#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { PublicClientApplication, type ICachePlugin, type TokenCacheContext } from "@azure/msal-node";
import { Client, ResponseType } from "@microsoft/microsoft-graph-client";
import "isomorphic-fetch";
import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";
import {
  createOneDriveFolder,
  getOneDriveItemMetadata,
  listOneDriveFolder,
  moveOneDriveItem,
} from "./onedrive.js";

dotenv.config({ path: path.join(__dirname, "../.env") });

const CLIENT_ID = process.env.CLIENT_ID ?? "1950a258-227b-4e31-a9cf-717495945fc2";
const TENANT_ID = process.env.TENANT_ID ?? "common";

// Raíz del proyecto (un nivel por encima de dist/). Claude Code arranca este server desde
// un CWD arbitrario (normalmente el HOME del usuario), así que NUNCA hay que confiar en rutas
// relativas al CWD: una ruta relativa en .env haría que el token no se encuentre y el server
// respondería "No active session found" aunque la sesión exista. Por eso resolvemos siempre
// TOKEN_CACHE_PATH a una ruta absoluta anclada a la raíz del proyecto. (Bug histórico, ver README.)
const PROJECT_ROOT = path.join(__dirname, "..");
const resolveFromRoot = (p: string) => (path.isAbsolute(p) ? p : path.join(PROJECT_ROOT, p));

const TOKEN_CACHE_PATH = resolveFromRoot(process.env.TOKEN_CACHE_PATH ?? ".token_cache.json");
const DOWNLOAD_PATH = process.env.DOWNLOAD_PATH ?? path.join(process.env.HOME ?? "~", "Downloads", "m365-mcp");

const GRAPH_SCOPES = [
  "User.Read",
  "Mail.Read",
  "Mail.ReadWrite",
  "Mail.Send",
  "Calendars.ReadWrite",
  "Files.ReadWrite.All",
  "Tasks.ReadWrite",
  "Contacts.ReadWrite",
  "Notes.ReadWrite",
  "OnlineMeetings.ReadWrite",
  "People.Read",
  "Presence.Read",
  "Sites.ReadWrite.All",
  "Chat.ReadWrite",
  "MailboxSettings.ReadWrite",
  "offline_access",
];

// ─── Token Cache ──────────────────────────────────────────────────────────────

const cachePlugin: ICachePlugin = {
  async beforeCacheAccess(ctx: TokenCacheContext) {
    if (fs.existsSync(TOKEN_CACHE_PATH)) {
      ctx.tokenCache.deserialize(fs.readFileSync(TOKEN_CACHE_PATH, "utf-8"));
    }
  },
  async afterCacheAccess(ctx: TokenCacheContext) {
    if (ctx.cacheHasChanged) {
      fs.writeFileSync(TOKEN_CACHE_PATH, ctx.tokenCache.serialize());
    }
  },
};

async function getAccessToken(): Promise<string> {
  const msalApp = new PublicClientApplication({
    auth: {
      clientId: CLIENT_ID,
      authority: `https://login.microsoftonline.com/${TENANT_ID}`,
    },
    cache: { cachePlugin },
  });

  const accounts = await msalApp.getTokenCache().getAllAccounts();

  if (accounts.length > 0) {
    try {
      const result = await msalApp.acquireTokenSilent({
        account: accounts[0],
        scopes: GRAPH_SCOPES,
      });
      if (result?.accessToken) return result.accessToken;
    } catch {
      // Token expired — needs re-auth
    }
  }

  throw new Error(
    "No active session found. Run 'npm run auth' in the m365-mcp-server directory to authenticate first."
  );
}

function graphClient(token: string): Client {
  return Client.init({ authProvider: (done) => done(null, token) });
}

// ─── Tool: search_onedrive_files ──────────────────────────────────────────────

async function searchOneDriveFiles(args: { query: string; top?: number }) {
  const client = graphClient(await getAccessToken());
  const res = await client
    .api(`/me/drive/root/search(q='${encodeURIComponent(args.query)}')`)
    .select("id,name,webUrl,size,lastModifiedDateTime,file")
    .top(args.top ?? 20)
    .get();
  return (res.value as any[]).map((f) => ({
    id: f.id,
    name: f.name,
    webUrl: f.webUrl,
    size: f.size,
    lastModified: f.lastModifiedDateTime,
    mimeType: f.file?.mimeType,
  }));
}

// ─── Tool: download_onedrive_file ─────────────────────────────────────────────

async function downloadOneDriveFile(args: { file_id: string; file_name?: string }) {
  const client = graphClient(await getAccessToken());
  const meta = await client.api(`/me/drive/items/${args.file_id}`).get();
  const name: string = args.file_name ?? meta.name ?? "file";
  const ext = path.extname(name).toLowerCase();
  const textTypes = [".txt", ".md", ".json", ".csv", ".html", ".xml", ".ts", ".js", ".py", ".yaml", ".toml"];

  // /content bajo fetch/undici devuelve un web ReadableStream (sin .pipe); pedimos
  // ARRAYBUFFER para no mezclar web streams con Node streams.
  const raw = await client
    .api(`/me/drive/items/${args.file_id}/content`)
    .responseType(ResponseType.ARRAYBUFFER)
    .get();
  const buf = Buffer.isBuffer(raw) ? raw : Buffer.from(raw as ArrayBuffer);

  if (textTypes.includes(ext)) {
    return { name, type: "text", content: buf.toString("utf-8") };
  }

  if (!fs.existsSync(DOWNLOAD_PATH)) fs.mkdirSync(DOWNLOAD_PATH, { recursive: true });
  const dest = path.join(DOWNLOAD_PATH, name);
  fs.writeFileSync(dest, buf);
  return { name, type: "binary", savedTo: dest, size: buf.length };
}

// ─── Tool: upload_onedrive_file ───────────────────────────────────────────────

async function uploadOneDriveFile(args: { file_name: string; content: string; folder_path?: string }) {
  const client = graphClient(await getAccessToken());
  const remotePath = args.folder_path ? `${args.folder_path}/${args.file_name}` : args.file_name;
  const res = await client
    .api(`/me/drive/root:/${remotePath}:/content`)
    .put(Buffer.from(args.content, "utf-8"));
  return { id: res.id, name: res.name, webUrl: res.webUrl, size: res.size };
}

async function listOneDriveFolderTool(args: { folder_id?: string; top?: number; next_page_url?: string }) {
  return listOneDriveFolder(graphClient(await getAccessToken()), args);
}

async function getOneDriveItemMetadataTool(args: { item_id: string }) {
  return getOneDriveItemMetadata(graphClient(await getAccessToken()), args);
}

async function createOneDriveFolderTool(args: { name: string; parent_id?: string }) {
  return createOneDriveFolder(graphClient(await getAccessToken()), args);
}

async function moveOneDriveItemTool(args: {
  item_id: string;
  destination_folder_id: string;
  expected_parent_id: string;
  expected_name: string;
}) {
  return moveOneDriveItem(graphClient(await getAccessToken()), args);
}

// ─── Tool: update_excel_sheet ─────────────────────────────────────────────────

async function updateExcelSheet(args: {
  file_id: string;
  sheet_name: string;
  action: "read" | "write";
  range?: string;
  values?: unknown[][];
}) {
  const client = graphClient(await getAccessToken());
  const base = `/me/drive/items/${args.file_id}/workbook/worksheets/${encodeURIComponent(args.sheet_name)}`;

  if (args.action === "read") {
    const endpoint = args.range ? `${base}/range(address='${args.range}')` : `${base}/usedRange`;
    const res = await client.api(endpoint).get();
    return { values: res.values, address: res.address, rowCount: res.rowCount, columnCount: res.columnCount };
  }

  if (!args.range || !args.values) throw new Error("'range' and 'values' are required for write action");
  const res = await client.api(`${base}/range(address='${args.range}')`).patch({ values: args.values });
  return { address: res.address, updated: true };
}

// ─── Tool: get_latest_emails ──────────────────────────────────────────────────

async function getLatestEmails(args: {
  top?: number;
  sender?: string;
  subject?: string;
  unread_only?: boolean;
}) {
  const client = graphClient(await getAccessToken());
  const filters: string[] = [];
  if (args.sender) filters.push(`from/emailAddress/address eq '${args.sender}'`);
  if (args.subject) filters.push(`contains(subject,'${args.subject}')`);
  if (args.unread_only) filters.push("isRead eq false");

  let req = client
    .api("/me/messages")
    .top(args.top ?? 10)
    .orderby("receivedDateTime desc")
    .select("id,subject,from,receivedDateTime,isRead,bodyPreview,hasAttachments");

  if (filters.length > 0) req = req.filter(filters.join(" and "));
  const res = await req.get();
  return (res.value as any[]).map((m) => ({
    id: m.id,
    subject: m.subject,
    from: m.from?.emailAddress,
    received: m.receivedDateTime,
    isRead: m.isRead,
    preview: m.bodyPreview,
    hasAttachments: m.hasAttachments,
  }));
}

// ─── Tool: send_outlook_email ─────────────────────────────────────────────────

async function sendOutlookEmail(args: {
  to: string[];
  subject: string;
  body: string;
  is_html?: boolean;
  cc?: string[];
}) {
  const client = graphClient(await getAccessToken());
  await client.api("/me/sendMail").post({
    message: {
      subject: args.subject,
      body: { contentType: args.is_html ? "HTML" : "Text", content: args.body },
      toRecipients: args.to.map((a) => ({ emailAddress: { address: a } })),
      ccRecipients: (args.cc ?? []).map((a) => ({ emailAddress: { address: a } })),
    },
  });
  return { sent: true, to: args.to, subject: args.subject };
}

// ─── Tool: download_email_attachments ────────────────────────────────────────

async function downloadEmailAttachments(args: { message_id: string; save_path?: string }) {
  const client = graphClient(await getAccessToken());
  const savePath = args.save_path ?? DOWNLOAD_PATH;
  if (!fs.existsSync(savePath)) fs.mkdirSync(savePath, { recursive: true });

  const res = await client.api(`/me/messages/${args.message_id}/attachments`).get();
  const saved: string[] = [];
  for (const att of res.value as any[]) {
    if (att["@odata.type"] === "#microsoft.graph.fileAttachment") {
      const dest = path.join(savePath, att.name);
      fs.writeFileSync(dest, Buffer.from(att.contentBytes, "base64"));
      saved.push(dest);
    }
  }
  return { savedFiles: saved, count: saved.length };
}

// ─── Tool: manage_todo_tasks ──────────────────────────────────────────────────

async function manageTodoTasks(args: {
  action: "list_lists" | "list_tasks" | "create_task" | "complete_task";
  list_id?: string;
  task_id?: string;
  title?: string;
  due_date?: string;
  notes?: string;
}) {
  const client = graphClient(await getAccessToken());

  switch (args.action) {
    case "list_lists": {
      const res = await client.api("/me/todo/lists").get();
      return (res.value as any[]).map((l) => ({ id: l.id, name: l.displayName, isOwner: l.isOwner }));
    }
    case "list_tasks": {
      if (!args.list_id) throw new Error("list_id required");
      const res = await client.api(`/me/todo/lists/${args.list_id}/tasks`).get();
      return (res.value as any[]).map((t) => ({
        id: t.id,
        title: t.title,
        status: t.status,
        dueDate: t.dueDateTime,
        importance: t.importance,
      }));
    }
    case "create_task": {
      if (!args.list_id || !args.title) throw new Error("list_id and title required");
      const body: Record<string, unknown> = { title: args.title };
      if (args.due_date) body.dueDateTime = { dateTime: args.due_date, timeZone: "UTC" };
      if (args.notes) body.body = { content: args.notes, contentType: "text" };
      const res = await client.api(`/me/todo/lists/${args.list_id}/tasks`).post(body);
      return { id: res.id, title: res.title, status: res.status };
    }
    case "complete_task": {
      if (!args.list_id || !args.task_id) throw new Error("list_id and task_id required");
      const res = await client
        .api(`/me/todo/lists/${args.list_id}/tasks/${args.task_id}`)
        .patch({ status: "completed" });
      return { id: res.id, title: res.title, status: res.status };
    }
    default:
      throw new Error(`Unknown action: ${String(args.action)}`);
  }
}

// ─── Tool: sync_calendar_events ───────────────────────────────────────────────

async function syncCalendarEvents(args: {
  action: "list" | "create";
  top?: number;
  start_date?: string;
  end_date?: string;
  subject?: string;
  body?: string;
  start_datetime?: string;
  end_datetime?: string;
  timezone?: string;
  attendees?: string[];
}) {
  const client = graphClient(await getAccessToken());

  if (args.action === "list") {
    const filters: string[] = [];
    if (args.start_date) filters.push(`start/dateTime ge '${args.start_date}'`);
    if (args.end_date) filters.push(`end/dateTime le '${args.end_date}'`);
    let req = client
      .api("/me/events")
      .top(args.top ?? 20)
      .orderby("start/dateTime")
      .select("id,subject,start,end,location,organizer,bodyPreview");
    if (filters.length > 0) req = req.filter(filters.join(" and "));
    const res = await req.get();
    return (res.value as any[]).map((e) => ({
      id: e.id,
      subject: e.subject,
      start: e.start,
      end: e.end,
      location: e.location?.displayName,
      organizer: e.organizer?.emailAddress,
      preview: e.bodyPreview,
    }));
  }

  if (!args.subject || !args.start_datetime || !args.end_datetime) {
    throw new Error("subject, start_datetime, and end_datetime required for create");
  }
  const tz = args.timezone ?? "UTC";
  const event: Record<string, unknown> = {
    subject: args.subject,
    body: { contentType: "HTML", content: args.body ?? "" },
    start: { dateTime: args.start_datetime, timeZone: tz },
    end: { dateTime: args.end_datetime, timeZone: tz },
  };
  if (args.attendees?.length) {
    event.attendees = args.attendees.map((a) => ({ emailAddress: { address: a }, type: "required" }));
  }
  const res = await client.api("/me/events").post(event);
  return { id: res.id, subject: res.subject, start: res.start, end: res.end, webLink: res.webLink };
}

// ─── MCP Tool Definitions ─────────────────────────────────────────────────────

const TOOLS = [
  {
    name: "search_onedrive_files",
    description: "Search files in OneDrive by name, keyword or extension",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Search term: filename, extension (.xlsx), or keyword" },
        top: { type: "number", description: "Max results (default 20)" },
      },
      required: ["query"],
    },
  },
  {
    name: "download_onedrive_file",
    description: "Read text/JSON/CSV/Markdown file content from OneDrive, or download binary files to ~/Downloads/m365-mcp",
    inputSchema: {
      type: "object",
      properties: {
        file_id: { type: "string", description: "OneDrive item ID obtained from search_onedrive_files" },
        file_name: { type: "string", description: "Filename with extension (ensures correct type handling)" },
      },
      required: ["file_id"],
    },
  },
  {
    name: "upload_onedrive_file",
    description: "Create or overwrite a file in OneDrive with provided text content",
    inputSchema: {
      type: "object",
      properties: {
        file_name: { type: "string", description: "Target filename including extension" },
        content: { type: "string", description: "File content (text, JSON, CSV, Markdown, etc.)" },
        folder_path: { type: "string", description: "OneDrive folder path e.g. 'Documents/Reports' (optional)" },
      },
      required: ["file_name", "content"],
    },
  },
  {
    name: "update_excel_sheet",
    description: "Read or write cells and ranges in an Excel workbook stored on OneDrive",
    inputSchema: {
      type: "object",
      properties: {
        file_id: { type: "string", description: "OneDrive item ID of the Excel file" },
        sheet_name: { type: "string", description: "Worksheet name (e.g. 'Sheet1')" },
        action: { type: "string", enum: ["read", "write"] },
        range: { type: "string", description: "Cell range e.g. 'A1:D10'. Omit for full usedRange on read." },
        values: {
          type: "array",
          description: "2D array of values for write e.g. [[1,'a'],[2,'b']]",
          items: { type: "array" },
        },
      },
      required: ["file_id", "sheet_name", "action"],
    },
  },
  {
    name: "list_onedrive_folder",
    description: "List files and folders in the OneDrive root or in a folder selected by its stable item ID",
    inputSchema: {
      type: "object",
      properties: {
        folder_id: { type: "string", description: "Folder item ID. Omit to list the OneDrive root." },
        top: { type: "number", description: "Maximum total results, from 1 to 1000 (default 100)" },
        next_page_url: { type: "string", description: "Continuation URL returned by a previous call; only Microsoft Graph URLs are accepted" },
      },
      required: [],
    },
  },
  {
    name: "get_onedrive_item_metadata",
    description: "Get safe metadata for a OneDrive file or folder by its stable item ID",
    inputSchema: {
      type: "object",
      properties: { item_id: { type: "string", description: "OneDrive item ID" } },
      required: ["item_id"],
    },
  },
  {
    name: "create_onedrive_folder",
    description: "Create a OneDrive folder. Fails instead of renaming when a sibling already has the same name.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "New folder name" },
        parent_id: { type: "string", description: "Parent folder item ID. Omit to create in root." },
      },
      required: ["name"],
    },
  },
  {
    name: "move_onedrive_item",
    description: "Move a OneDrive file or folder using stable item IDs. Does not delete content.",
    inputSchema: {
      type: "object",
      properties: {
        item_id: { type: "string", description: "ID of the file or folder to move" },
        destination_folder_id: { type: "string", description: "ID of the destination folder" },
        expected_parent_id: { type: "string", description: "Current parent ID observed during inventory; aborts if stale" },
        expected_name: { type: "string", description: "Current item name observed during inventory; aborts if stale" },
      },
      required: ["item_id", "destination_folder_id", "expected_parent_id", "expected_name"],
    },
  },
  {
    name: "get_latest_emails",
    description: "Retrieve recent emails from Outlook with optional filters",
    inputSchema: {
      type: "object",
      properties: {
        top: { type: "number", description: "Number of emails (default 10)" },
        sender: { type: "string", description: "Filter by sender address" },
        subject: { type: "string", description: "Filter by subject keyword" },
        unread_only: { type: "boolean", description: "Only return unread emails" },
      },
      required: [],
    },
  },
  {
    name: "send_outlook_email",
    description: "Compose and send an email via Outlook",
    inputSchema: {
      type: "object",
      properties: {
        to: { type: "array", items: { type: "string" }, description: "Recipient email addresses" },
        subject: { type: "string" },
        body: { type: "string", description: "Email body (plain text or HTML)" },
        is_html: { type: "boolean", description: "Set true if body contains HTML" },
        cc: { type: "array", items: { type: "string" }, description: "CC recipients (optional)" },
      },
      required: ["to", "subject", "body"],
    },
  },
  {
    name: "download_email_attachments",
    description: "Download and save all file attachments from a specific email",
    inputSchema: {
      type: "object",
      properties: {
        message_id: { type: "string", description: "Email ID from get_latest_emails" },
        save_path: { type: "string", description: "Local folder path (default ~/Downloads/m365-mcp)" },
      },
      required: ["message_id"],
    },
  },
  {
    name: "manage_todo_tasks",
    description: "List task lists, list tasks, create a task, or mark a task as completed in Microsoft To-Do",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list_lists", "list_tasks", "create_task", "complete_task"],
        },
        list_id: { type: "string", description: "Task list ID (required for list_tasks, create_task, complete_task)" },
        task_id: { type: "string", description: "Task ID (required for complete_task)" },
        title: { type: "string", description: "Task title (required for create_task)" },
        due_date: { type: "string", description: "Due date ISO8601 e.g. '2025-12-31T10:00:00'" },
        notes: { type: "string", description: "Task notes" },
      },
      required: ["action"],
    },
  },
  {
    name: "sync_calendar_events",
    description: "List upcoming calendar events or create a new event",
    inputSchema: {
      type: "object",
      properties: {
        action: { type: "string", enum: ["list", "create"] },
        top: { type: "number", description: "Max events to list (default 20)" },
        start_date: { type: "string", description: "Filter from date ISO8601" },
        end_date: { type: "string", description: "Filter until date ISO8601" },
        subject: { type: "string", description: "Event title (required for create)" },
        body: { type: "string", description: "Event description (HTML supported)" },
        start_datetime: { type: "string", description: "Start datetime ISO8601 (required for create)" },
        end_datetime: { type: "string", description: "End datetime ISO8601 (required for create)" },
        timezone: { type: "string", description: "Timezone e.g. 'Europe/Madrid' (default UTC)" },
        attendees: { type: "array", items: { type: "string" }, description: "Attendee emails" },
      },
      required: ["action"],
    },
  },
];

// ─── MCP Server ───────────────────────────────────────────────────────────────

const server = new Server(
  { name: "m365-personal-suite", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;
  try {
    let result: unknown;
    switch (name) {
      case "search_onedrive_files":      result = await searchOneDriveFiles(args as any); break;
      case "download_onedrive_file":     result = await downloadOneDriveFile(args as any); break;
      case "upload_onedrive_file":       result = await uploadOneDriveFile(args as any); break;
      case "list_onedrive_folder":       result = await listOneDriveFolderTool(args as any); break;
      case "get_onedrive_item_metadata": result = await getOneDriveItemMetadataTool(args as any); break;
      case "create_onedrive_folder":     result = await createOneDriveFolderTool(args as any); break;
      case "move_onedrive_item":         result = await moveOneDriveItemTool(args as any); break;
      case "update_excel_sheet":         result = await updateExcelSheet(args as any); break;
      case "get_latest_emails":          result = await getLatestEmails(args as any); break;
      case "send_outlook_email":         result = await sendOutlookEmail(args as any); break;
      case "download_email_attachments": result = await downloadEmailAttachments(args as any); break;
      case "manage_todo_tasks":          result = await manageTodoTasks(args as any); break;
      case "sync_calendar_events":       result = await syncCalendarEvents(args as any); break;
      default: throw new Error(`Unknown tool: ${name}`);
    }
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write("M365 Personal Suite MCP Server — ready\n");
}

main().catch((err) => {
  process.stderr.write(`Fatal error: ${String(err)}\n`);
  process.exit(1);
});

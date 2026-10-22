# M365 Personal Suite — MCP Server + Telegram Bot

A local **Model Context Protocol** server that exposes Microsoft 365 (Outlook,
OneDrive, Excel, Calendar, To Do) to an MCP client over `stdio`, plus an optional
Telegram mail bot written with the Python standard library.

**13 tools. Read and write. One user. Local process. No hosted service.**

> Independent software, not affiliated with Microsoft, Anthropic or Telegram.

## Tools

| Tool | What it does | Effect |
|---|---|---|
| `search_onedrive_files` | Search files | Remote read |
| `list_onedrive_folder` | List a folder by ID, paginated | Remote read |
| `get_onedrive_item_metadata` | Metadata by ID | Remote read |
| `create_onedrive_folder` | Create a folder | Remote write |
| `move_onedrive_item` | Move an item, checking expected name and parent | Remote write |
| `download_onedrive_file` | Return text or save a binary | Remote read, local write |
| `upload_onedrive_file` | Create or overwrite a text file | Remote write |
| `update_excel_sheet` | Read or write a workbook range | Remote read/write |
| `get_latest_emails` | Recent mail with filters | Remote read |
| `send_outlook_email` | Send mail (optional HTML and CC) | **Immediate send** |
| `download_email_attachments` | Save attachments | Remote read, local write |
| `manage_todo_tasks` | List, create, complete tasks | Remote read/write |
| `sync_calendar_events` | List or create events | Remote read/write |

## Safety model

Write tools execute when called. There is no hidden approval loop; the server gives
you three explicit policies instead (set in `.env`, see `.env.example`).
**Scope:** `M365_READ_ONLY` and `M365_MINIMAL_SCOPES` apply to **both** the MCP server and
the Telegram bot. `M365_CONFIRM_WRITES` applies to the MCP server only: the bot already
has its own two-step confirmation buttons.

| Variable | Effect |
|---|---|
| `M365_READ_ONLY=1` | **All** writes are blocked; reads keep working |
| `M365_CONFIRM_WRITES=1` | Every write must carry `"confirm": true` (two-step) |
| `M365_MINIMAL_SCOPES=1` | Sign-in requests only the scopes the server actually uses |

Design properties:

- **Fail-closed tool classification.** A tool whose action is unknown counts as a write,
  so a new tool cannot silently bypass read-only mode (`src/policy.ts`).
- **Smallest useful scope set.** `M365_MINIMAL_SCOPES=1` drops `Mail.ReadWrite`,
  `Sites.ReadWrite.All`, `Chat.ReadWrite`, `Contacts`, `Notes`, `OnlineMeetings`,
  `MailboxSettings`, `Presence` and `People`; `Files.ReadWrite.All` stays because the
  OneDrive/Excel tools need it. Default is unchanged so existing sessions keep working.
- **No shell.** The browser is opened with an argv list (`spawn`), never `exec`.
- **Untrusted input is validated at the boundary** before touching disk, URL or OData:
  attachment names (no path traversal, no overwrite), OData literals escaped, Graph IDs
  encoded, Excel ranges checked (A1), `top` clamped.
- **Token cache is owner-only** (file `0600`, folder `0700`).
- **Rate limits:** Graph `429`/`503`/`504` are retried (3 attempts, honours `Retry-After`),
  **except `POST`** — `sendMail`/event creation are not idempotent and a retry could
  duplicate the email or the invitation.
- **Telegram messages > 4096 chars are split**, keyboard attached to the last chunk.

## Requirements

- Git, npm, Node.js (CI uses **22**).
- Python for the bot and its tests (CI uses **3.11**, `pytest`).
- A Microsoft account and an Entra/Azure app registration with the delegated
  permissions you actually use.
- An MCP client with `stdio` transport (example config for Claude Code).

API availability depends on account type, permissions and Microsoft policy. The
project offers no hosted service and no multi-user isolation.

## Install

```bash
git clone https://github.com/lfpalomaresg/m365-mcp-server.git
cd m365-mcp-server
npm ci
npm run build
```

`npm ci` uses the lockfile. The build writes `dist/`; it does not sign in and does not
connect to a mailbox.

### Configure

1. Copy `.env.example` to `.env` **only if it does not exist yet** and edit it locally.
2. Set `CLIENT_ID` and `TENANT_ID` (`common` allows multiple account types, subject to
   your app registration).
3. Set an absolute `DOWNLOAD_PATH` and, optionally, `TOKEN_CACHE_PATH`
   (relative paths resolve against the project root; if omitted,
   `~/.m365-mcp/.token_cache.json`).

### App registration and sign-in

Register `http://localhost:3000` as a redirect URI for a desktop/public client. The
exact permission list is `resolveScopes()` in [`src/policy.ts`](src/policy.ts) — review
it before granting. `npm run auth` starts the local callback and opens the browser.

### MCP client

```json
{
  "mcpServers": {
    "m365": {
      "command": "node",
      "args": ["/absolute/path/to/m365-mcp-server/dist/index.js"]
    }
  }
}
```

## Privacy

- `.env` and the token cache are sensitive: do not publish them or paste them into issues.
- The cache is a local file, not an encrypted vault. The code applies restrictive POSIX
  permissions; check your OS access control too.
- Content you query is returned to the MCP client (and therefore to whatever model the
  client uses). The Telegram bot transmits what it shows to Telegram.
- Downloads go to `DOWNLOAD_PATH` or the path given to the tool — review what you store.

## Tests

```bash
npm test     # tsc + node --test (41) + pytest (91), no network, no real accounts
```

Fictional values and simulated services only. The suite verifies validation, simulated
OneDrive/Graph operations, token cache, the MCP contract, the bot and the setup wizard.
**It does not prove a real sign-in or a live Graph/Telegram round trip.**

## Known limits

- Single user, no per-user isolation, no hosted deployment.
- Tool descriptions are English; the bot's operator-facing messages are Spanish.
- `download_email_attachments` and `download_onedrive_file` write to local disk by design.
- Compatibility is documented for Claude Code; other MCP clients are not certified.

## License

MIT. See [LICENSE](LICENSE).

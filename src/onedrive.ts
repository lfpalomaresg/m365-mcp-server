type GraphRequest = {
  select(value: string): GraphRequest;
  top(value: number): GraphRequest;
  header(name: string, value: string): GraphRequest;
  get(): Promise<any>;
  post(body: unknown): Promise<any>;
  patch(body: unknown): Promise<any>;
};

export type GraphClientLike = { api(endpoint: string): GraphRequest };

const ITEM_FIELDS = "id,name,webUrl,size,createdDateTime,lastModifiedDateTime,parentReference,file,folder";

function itemEndpoint(itemId: string, suffix = ""): string {
  if (!itemId.trim()) throw new Error("item_id cannot be empty");
  return `/me/drive/items/${encodeURIComponent(itemId)}${suffix}`;
}

function projectItem(item: any) {
  return {
    id: item.id,
    name: item.name,
    type: item.folder ? "folder" : "file",
    webUrl: item.webUrl,
    size: item.size,
    created: item.createdDateTime,
    lastModified: item.lastModifiedDateTime,
    parentId: item.parentReference?.id,
    childCount: item.folder?.childCount,
    mimeType: item.file?.mimeType,
  };
}

export async function listOneDriveFolder(
  client: GraphClientLike,
  args: { folder_id?: string; top?: number; next_page_url?: string },
) {
  const endpoint = args.next_page_url
    ?? (args.folder_id ? itemEndpoint(args.folder_id, "/children") : "/me/drive/root/children");
  const limit = Math.max(1, Math.min(Math.trunc(args.top ?? 100), 1000));
  const items: any[] = [];
  let nextEndpoint: string | null = endpoint;

  while (nextEndpoint && items.length < limit) {
    if (nextEndpoint.startsWith("http")) {
      const url = new URL(nextEndpoint);
      if (
        url.protocol !== "https:"
        || url.hostname !== "graph.microsoft.com"
        || !url.pathname.startsWith("/v1.0/me/drive/")
      ) {
        throw new Error("Graph returned an invalid pagination URL");
      }
    }
    const response = await client
      .api(nextEndpoint)
      .select(ITEM_FIELDS)
      .top(Math.min(200, limit - items.length))
      .get();
    items.push(...(response.value ?? []));
    nextEndpoint = response["@odata.nextLink"] ?? null;
  }
  return {
    items: items.slice(0, limit).map(projectItem),
    complete: nextEndpoint === null,
    nextPageUrl: nextEndpoint,
  };
}

export async function getOneDriveItemMetadata(client: GraphClientLike, args: { item_id: string }) {
  return projectItem(await client.api(itemEndpoint(args.item_id)).select(ITEM_FIELDS).get());
}

export async function createOneDriveFolder(client: GraphClientLike, args: { name: string; parent_id?: string }) {
  if (args.name !== args.name.trim() || args.name.endsWith(".")) throw new Error("Invalid OneDrive folder name");
  const name = args.name.trim();
  const baseName = name.split(".")[0].toUpperCase();
  const reserved = new Set(["CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"]);
  if (!name || name === "." || name === ".." || name.toLowerCase() === "desktop.ini" || reserved.has(baseName) || /[\\/:*?"<>|]/.test(name)) {
    throw new Error("Invalid OneDrive folder name");
  }
  const endpoint = args.parent_id ? itemEndpoint(args.parent_id, "/children") : "/me/drive/root/children";
  return projectItem(await client.api(endpoint).post({
    name,
    folder: {},
    "@microsoft.graph.conflictBehavior": "fail",
  }));
}

export async function moveOneDriveItem(
  client: GraphClientLike,
  args: { item_id: string; destination_folder_id: string; expected_parent_id: string; expected_name: string },
) {
  if (args.item_id === args.destination_folder_id) throw new Error("An item cannot be moved into itself");
  const current = await client.api(itemEndpoint(args.item_id)).select("id,name,parentReference,eTag").get();
  if (current.name !== args.expected_name || current.parentReference?.id !== args.expected_parent_id) {
    throw new Error("Item changed since inventory; move aborted");
  }
  const eTag = current.eTag ?? current["@odata.etag"];
  if (!eTag) throw new Error("Item has no eTag; safe move aborted");
  const destination = await client.api(itemEndpoint(args.destination_folder_id)).select("id,name,folder").get();
  if (!destination.folder) throw new Error("Destination item is not a folder");
  return projectItem(await client
    .api(itemEndpoint(args.item_id))
    .header("If-Match", eTag)
    .patch({
      parentReference: { id: args.destination_folder_id },
      "@microsoft.graph.conflictBehavior": "fail",
    }));
}

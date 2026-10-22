/**
 * Políticas de seguridad del servidor MCP, sin dependencias y sin efectos:
 * se prueban con `node --test` sin token, sin red y sin Microsoft 365.
 *
 * Tres decisiones viven aquí:
 *  1. Qué scopes se piden (mínimos o completos).
 *  2. Qué herramientas escriben de verdad (según su acción).
 *  3. Cómo abrir el navegador sin pasar por una shell.
 */

export type ToolAction = "read" | "write";

/** Scopes que el servidor MCP usa de verdad (índice en `index.ts`). */
export const MINIMAL_SCOPES = [
  "User.Read",
  "Mail.Read",
  "Mail.Send",
  "Calendars.ReadWrite",
  "Files.ReadWrite.All",
  "Tasks.ReadWrite",
  "offline_access",
];

/**
 * Scopes históricos del login. Incluyen permisos que el servidor no usa
 * (Contacts, Notes, Sites, Chat, Presence, People, Meetings, MailboxSettings…).
 * Se mantienen por defecto para no invalidar sesiones ya concedidas; con
 * `M365_MINIMAL_SCOPES=1` el login pide solo MINIMAL_SCOPES.
 */
export const FULL_SCOPES = [
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

export function resolveScopes(env: NodeJS.ProcessEnv = process.env): string[] {
  return env.M365_MINIMAL_SCOPES === "1" ? [...MINIMAL_SCOPES] : [...FULL_SCOPES];
}

/** Herramientas cuyo efecto depende de `action`. Las demás son fijas. */
const ACTION_SCOPED: Record<string, { read: string[]; write: string[] }> = {
  update_excel_sheet: { read: ["read"], write: ["write"] },
  manage_todo_tasks: { read: ["list_lists", "list_tasks"], write: ["create_task", "complete_task"] },
  sync_calendar_events: { read: ["list"], write: ["create"] },
};

const READ_ONLY_TOOLS = new Set([
  "search_onedrive_files",
  "download_onedrive_file",
  "list_onedrive_folder",
  "get_onedrive_item_metadata",
  "get_latest_emails",
  "download_email_attachments",
]);

const WRITE_TOOLS = new Set([
  "upload_onedrive_file",
  "create_onedrive_folder",
  "move_onedrive_item",
  "send_outlook_email",
]);

/** ¿Esta llamada modifica datos remotos? Fail-closed: lo desconocido es escritura. */
export function isWriteCall(name: string, args: Record<string, unknown> = {}): boolean {
  const scoped = ACTION_SCOPED[name];
  if (scoped) {
    const action = typeof args.action === "string" ? args.action : "";
    if (scoped.read.includes(action)) return false;
    return true;
  }
  if (READ_ONLY_TOOLS.has(name)) return false;
  if (WRITE_TOOLS.has(name)) return true;
  // Fail-closed: una herramienta nueva que nadie clasifique se trata como escritura.
  return true;
}

export class PolicyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PolicyError";
  }
}

/**
 * Puerta de las llamadas. `M365_READ_ONLY=1` bloquea toda escritura;
 * `M365_CONFIRM_WRITES=1` exige `confirm: true` en los argumentos.
 */
export function assertToolAllowed(
  name: string,
  args: Record<string, unknown> = {},
  env: NodeJS.ProcessEnv = process.env,
): void {
  if (env.M365_READ_ONLY === "1" && isWriteCall(name, args)) {
    throw new PolicyError(
      `M365_READ_ONLY=1: "${name}" es una operación de escritura y está bloqueada en este servidor.`,
    );
  }
  if (env.M365_CONFIRM_WRITES === "1" && isWriteCall(name, args) && args.confirm !== true) {
    throw new PolicyError(
      `"${name}" modifica Microsoft 365: repite la llamada con "confirm": true para autorizarla.`,
    );
  }
}

/** argv para abrir una URL en el navegador, nunca una cadena de shell. */
export function openCommand(url: string, platform: NodeJS.Platform = process.platform): string[] {
  if (platform === "darwin") return ["open", url];
  // rundll32 recibe la URL como UN argumento: `cmd /c start` la corta en el
  // primer "&" de la query de MSAL y en Windows no se puede autenticar.
  if (platform === "win32") return ["rundll32", "url.dll,FileProtocolHandler", url];
  return ["xdg-open", url];
}

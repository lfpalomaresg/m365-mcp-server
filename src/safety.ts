import * as fs from "fs";
import * as path from "path";

// Builds a local destination for a name that comes from Graph (attachment or
// OneDrive item). The name is untrusted: "../../.zshrc" must not escape `dir`,
// and an existing file must not be silently overwritten.
export function safeLocalPath(dir: string, untrustedName: string): string {
  const last = String(untrustedName ?? "").split(/[\\/]/).pop() ?? "";
  // eslint-disable-next-line no-control-regex
  let name = last.replace(/[\x00-\x1f]/g, "").trim();
  if (!name || name === "." || name === "..") name = "attachment";

  const ext = path.extname(name);
  const stem = name.slice(0, name.length - ext.length);
  let candidate = path.join(dir, name);
  for (let n = 1; fs.existsSync(candidate); n++) {
    candidate = path.join(dir, `${stem} (${n})${ext}`);
  }
  return candidate;
}

// OData string literal: a single quote inside the value is escaped by doubling it.
// Without this, sender "x') or (isRead eq true" rewrites the $filter.
export function odataString(value: string): string {
  return `'${String(value).replace(/'/g, "''")}'`;
}

export function buildEmailFilter(args: { sender?: string; subject?: string; unread_only?: boolean }): string {
  const filters: string[] = [];
  if (args.sender) filters.push(`from/emailAddress/address eq ${odataString(args.sender)}`);
  if (args.subject) filters.push(`contains(subject,${odataString(args.subject)})`);
  if (args.unread_only) filters.push("isRead eq false");
  return filters.join(" and ");
}

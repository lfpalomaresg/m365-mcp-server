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

// One Graph path segment built from a caller-supplied id: "a/../b?x" must not
// change the endpoint the request hits.
export function idSegment(id: string | undefined, param: string): string {
  if (!id || !String(id).trim()) throw new Error(`${param} cannot be empty`);
  return encodeURIComponent(String(id));
}

// Excel range in A1 notation (cell, cell range, whole columns or rows). It is
// interpolated into range(address='...'), so nothing else is allowed through.
const CELL = /^\$?[A-Za-z]{1,3}\$?\d+$/;
const COL = /^\$?[A-Za-z]{1,3}$/;
const ROW = /^\$?\d+$/;

export function a1Range(range: string): string {
  const parts = String(range ?? "").split(":");
  const valid =
    (parts.length === 1 && CELL.test(parts[0]))
    || (parts.length === 2 && (
      (CELL.test(parts[0]) && CELL.test(parts[1]))
      || (COL.test(parts[0]) && COL.test(parts[1]))
      || (ROW.test(parts[0]) && ROW.test(parts[1]))
    ));
  if (!valid) throw new Error(`Invalid range: use A1 notation such as 'A1:D10'`);
  return range;
}

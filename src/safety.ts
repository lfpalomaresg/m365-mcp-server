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

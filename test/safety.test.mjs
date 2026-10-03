import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { buildEmailFilter, odataString, safeLocalPath } from "../dist/safety.js";

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "m365-safety-"));
}

test("safeLocalPath keeps attachment names inside the target folder", () => {
  const dir = tmpDir();
  for (const evil of ["../../.zshrc", "/etc/passwd", "..\\..\\evil.bat", "sub/dir/x.txt"]) {
    const dest = safeLocalPath(dir, evil);
    assert.equal(path.dirname(dest), dir, `escaped with ${evil}`);
  }
});

test("safeLocalPath falls back to a default name for empty or dot names", () => {
  const dir = tmpDir();
  for (const bad of ["", ".", "..", "   "]) {
    assert.equal(path.basename(safeLocalPath(dir, bad)), "attachment");
  }
});

test("safeLocalPath never overwrites an existing file", () => {
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, "report.pdf"), "old");
  assert.equal(path.basename(safeLocalPath(dir, "report.pdf")), "report (1).pdf");
  fs.writeFileSync(path.join(dir, "report (1).pdf"), "old");
  assert.equal(path.basename(safeLocalPath(dir, "report.pdf")), "report (2).pdf");
});

test("odataString doubles single quotes so values cannot close the literal", () => {
  assert.equal(odataString("O'Brien"), "'O''Brien'");
  assert.equal(odataString("x') or (isRead eq true"), "'x'') or (isRead eq true'");
});

test("buildEmailFilter escapes sender and subject", () => {
  assert.equal(
    buildEmailFilter({ sender: "a'b@x.com", subject: "it's", unread_only: true }),
    "from/emailAddress/address eq 'a''b@x.com' and contains(subject,'it''s') and isRead eq false",
  );
  assert.equal(buildEmailFilter({}), "");
});

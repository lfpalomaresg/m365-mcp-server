import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { a1Range, buildEmailFilter, clampTop, drivePath, idSegment, odataString, safeLocalPath } from "../dist/safety.js";

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

test("idSegment percent-encodes ids so they cannot add path segments or queries", () => {
  assert.equal(idSegment("AAMk/../me?x=1", "message_id"), "AAMk%2F..%2Fme%3Fx%3D1");
  assert.equal(idSegment("AQMkADAw=", "file_id"), "AQMkADAw%3D");
});

test("idSegment rejects empty ids with the parameter name", () => {
  assert.throws(() => idSegment("  ", "list_id"), /list_id cannot be empty/);
  assert.throws(() => idSegment(undefined, "task_id"), /task_id cannot be empty/);
});

test("a1Range accepts A1 references and ranges", () => {
  for (const ok of ["A1", "a1:d10", "$A$1:$B$2", "A:C", "3:7", "XFD1048576"]) {
    assert.equal(a1Range(ok), ok);
  }
});

test("a1Range rejects anything that could break out of range(address='...')", () => {
  for (const bad of ["A1')/x", "A1:B2'", "", "Sheet1!A1", "A1;B2", "ABCD1"]) {
    assert.throws(() => a1Range(bad), /Invalid range/, bad);
  }
});

test("clampTop bounds page sizes and falls back on junk", () => {
  assert.equal(clampTop(undefined, 10, 100), 10);
  assert.equal(clampTop(5000, 10, 100), 100);
  assert.equal(clampTop(0, 10, 100), 1);
  assert.equal(clampTop(-3, 10, 100), 1);
  assert.equal(clampTop(7.9, 10, 100), 7);
  assert.equal(clampTop("abc", 10, 100), 10);
  assert.equal(clampTop(Number.NaN, 10, 100), 10);
});

test("drivePath encodes each segment of an upload path", () => {
  assert.equal(drivePath("Documents/Informes 2026", "Q3 #1.md"), "Documents/Informes%202026/Q3%20%231.md");
  assert.equal(drivePath("/Docs//", "a.txt"), "Docs/a.txt");
  assert.equal(drivePath(undefined, "a.txt"), "a.txt");
});

test("drivePath rejects traversal, separators in the name and empty names", () => {
  assert.throws(() => drivePath("Docs/../..", "a.txt"), /Invalid OneDrive path/);
  assert.throws(() => drivePath("Docs", "../a.txt"), /Invalid OneDrive file name/);
  assert.throws(() => drivePath("Docs", "  "), /Invalid OneDrive file name/);
  assert.throws(() => drivePath("Docs", "a:b.txt"), /Invalid OneDrive file name/);
});

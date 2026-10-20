import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { resolveTokenCachePath } from "../dist/config.js";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));
const configModule = fileURLToPath(new URL("../dist/config.js", import.meta.url));

test("a relative cache configured by the user survives a foreign client CWD", () => {
  const elsewhere = fs.mkdtempSync(path.join(os.tmpdir(), "m365-cwd-"));
  try {
    const child = spawnSync(process.execPath, [
      "-e", "console.log(require(process.argv[1]).resolveTokenCachePath())", configModule,
    ], {
      cwd: elsewhere,
      env: { ...process.env, TOKEN_CACHE_PATH: "private/cache.json" },
      encoding: "utf8",
    });
    assert.equal(child.status, 0, child.stderr);
    assert.equal(child.stdout.trim(), path.join(projectRoot, "private", "cache.json"));
    assert.equal(fs.readdirSync(elsewhere).length, 0);
  } finally {
    fs.rmSync(elsewhere, { recursive: true, force: true });
  }
});

test("an existing absolute cache location is preserved", () => {
  const configured = path.join(os.tmpdir(), "m365-existing", "cache.json");
  assert.equal(resolveTokenCachePath(configured), configured);
});

test("empty configuration uses the legacy shared home cache", () => {
  const home = path.join(os.tmpdir(), "m365-home-example");
  for (const configured of ["", "   "]) {
    assert.equal(resolveTokenCachePath(configured, projectRoot, home),
      path.join(home, ".m365-mcp", ".token_cache.json"));
  }
});

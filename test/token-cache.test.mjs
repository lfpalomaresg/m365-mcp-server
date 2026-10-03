import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { fileCachePlugin } from "../dist/token-cache.js";

function fakeContext(changed, serialized = "{}") {
  const seen = { deserialized: null };
  return {
    seen,
    ctx: {
      cacheHasChanged: changed,
      tokenCache: {
        serialize: () => serialized,
        deserialize: (data) => { seen.deserialized = data; },
      },
    },
  };
}

const mode = (p) => fs.statSync(p).mode & 0o777;

test("token cache is created owner-only, including its folder", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "m365-cache-"));
  const cachePath = path.join(root, "nested", ".token_cache.json");
  const { ctx } = fakeContext(true, '{"AccessToken":{}}');
  await fileCachePlugin(cachePath).afterCacheAccess(ctx);
  assert.equal(fs.readFileSync(cachePath, "utf-8"), '{"AccessToken":{}}');
  assert.equal(mode(cachePath), 0o600);
  assert.equal(mode(path.dirname(cachePath)), 0o700);
});

test("an existing world-readable cache is tightened on write", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "m365-cache-"));
  const cachePath = path.join(root, ".token_cache.json");
  fs.writeFileSync(cachePath, "{}", { mode: 0o644 });
  fs.chmodSync(cachePath, 0o644);
  await fileCachePlugin(cachePath).afterCacheAccess(fakeContext(true).ctx);
  assert.equal(mode(cachePath), 0o600);
});

test("unchanged cache is not rewritten and existing cache is loaded", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "m365-cache-"));
  const cachePath = path.join(root, ".token_cache.json");
  await fileCachePlugin(cachePath).afterCacheAccess(fakeContext(false).ctx);
  assert.equal(fs.existsSync(cachePath), false);
  fs.writeFileSync(cachePath, "cached");
  const { ctx, seen } = fakeContext(false);
  await fileCachePlugin(cachePath).beforeCacheAccess(ctx);
  assert.equal(seen.deserialized, "cached");
});

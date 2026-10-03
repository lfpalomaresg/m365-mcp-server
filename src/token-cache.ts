import type { ICachePlugin, TokenCacheContext } from "@azure/msal-node";
import * as fs from "fs";
import * as path from "path";

// MSAL cache persisted to disk. It holds refresh tokens, so the file is
// owner-only (0600) and so is a folder we create for it (0700); a plain
// writeFileSync would leave it 0644 under the usual umask.
export function fileCachePlugin(cachePath: string): ICachePlugin {
  return {
    async beforeCacheAccess(ctx: TokenCacheContext) {
      if (fs.existsSync(cachePath)) {
        ctx.tokenCache.deserialize(fs.readFileSync(cachePath, "utf-8"));
      }
    },
    async afterCacheAccess(ctx: TokenCacheContext) {
      if (!ctx.cacheHasChanged) return;
      const dir = path.dirname(cachePath);
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
      fs.writeFileSync(cachePath, ctx.tokenCache.serialize(), { mode: 0o600 });
      fs.chmodSync(cachePath, 0o600);
    },
  };
}

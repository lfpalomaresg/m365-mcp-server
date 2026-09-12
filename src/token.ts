import { PublicClientApplication, type ICachePlugin, type TokenCacheContext } from "@azure/msal-node";
import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";

dotenv.config({ path: path.join(__dirname, "../.env") });

const CLIENT_ID = process.env.CLIENT_ID ?? "1950a258-227b-4e31-a9cf-717495945fc2";
const TENANT_ID = process.env.TENANT_ID ?? "common";

const PROJECT_ROOT = path.join(__dirname, "..");
const resolveFromRoot = (p: string) => (path.isAbsolute(p) ? p : path.join(PROJECT_ROOT, p)); 

const TOKEN_CACHE_PATH = resolveFromRoot(process.env.TOKEN_CACHE_PATH ?? ".token_cache.json");

const GRAPH_SCOPES = [
  "Mail.Read",
  "Mail.ReadWrite",
  "Mail.Send",
  "offline_access"
];

const cachePlugin: ICachePlugin = {
  async beforeCacheAccess(ctx: TokenCacheContext) {
    if (fs.existsSync(TOKEN_CACHE_PATH)) {
      ctx.tokenCache.deserialize(fs.readFileSync(TOKEN_CACHE_PATH, "utf-8"));
    }
  },
  async afterCacheAccess(ctx: TokenCacheContext) {
    if (ctx.cacheHasChanged) {
      fs.writeFileSync(TOKEN_CACHE_PATH, ctx.tokenCache.serialize());
    }
  },
};

async function printToken() {
  const msalApp = new PublicClientApplication({
    auth: {
      clientId: CLIENT_ID,
      authority: `https://login.microsoftonline.com/${TENANT_ID}`,
    },
    cache: { cachePlugin },
  });

  const accounts = await msalApp.getTokenCache().getAllAccounts();
  if (accounts.length > 0) {
    try {
      const result = await msalApp.acquireTokenSilent({
        account: accounts[0],
        scopes: GRAPH_SCOPES,
      });
      if (result?.accessToken) {
        console.log(result.accessToken);
        process.exit(0);
      }
    } catch (e) {
      // ignore
    }
  }
  console.error("ERROR: No active session. Run auth script first.");
  process.exit(1);
}

printToken().catch((err) => {
  console.error("ERROR: " + err.message);
  process.exit(1);
});

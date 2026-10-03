import { PublicClientApplication } from "@azure/msal-node";
import { fileCachePlugin } from "./token-cache.js";
import * as dotenv from "dotenv";
import * as os from "os";
import * as path from "path";

dotenv.config({ path: path.join(__dirname, "../.env") });

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(`${name} must be set in .env file.`);
  }
  return v;
}

const CLIENT_ID = requireEnv("CLIENT_ID");
const TENANT_ID = process.env.TENANT_ID ?? "common";

const TOKEN_DIR = path.join(os.homedir(), ".m365-mcp");
const TOKEN_CACHE_PATH = path.join(TOKEN_DIR, ".token_cache.json");

const GRAPH_SCOPES = [
  "Mail.Read",
  "Mail.ReadWrite",
  "Mail.Send",
  "offline_access"
];

const cachePlugin = fileCachePlugin(TOKEN_CACHE_PATH);

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

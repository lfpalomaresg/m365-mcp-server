#!/usr/bin/env node
import { PublicClientApplication, type ICachePlugin, type TokenCacheContext } from "@azure/msal-node";
import * as dotenv from "dotenv";
import * as fs from "fs";
import * as path from "path";
import * as http from "http";
import * as crypto from "crypto";
import { exec } from "child_process";

dotenv.config({ path: path.join(__dirname, "../.env") });

const CLIENT_ID = process.env.CLIENT_ID ?? "";
const TENANT_ID = process.env.TENANT_ID ?? "common";
const TOKEN_CACHE_PATH = process.env.TOKEN_CACHE_PATH ?? path.join(__dirname, "../.token_cache.json");
const REDIRECT_URI = "http://localhost:3000";

const GRAPH_SCOPES = [
  "User.Read",
  "Mail.Read",
  "Mail.ReadWrite",
  "Mail.Send",
  "Calendars.ReadWrite",
  "Files.ReadWrite.All",
  "Tasks.ReadWrite",
  "Contacts.ReadWrite",
  "Notes.ReadWrite",
  "OnlineMeetings.ReadWrite",
  "People.Read",
  "Presence.Read",
  "Sites.ReadWrite.All",
  "Chat.ReadWrite",
  "MailboxSettings.ReadWrite",
  "offline_access",
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

function base64URLEncode(buffer: Buffer): string {
  return buffer.toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

function generateCodeVerifier(): string {
  return base64URLEncode(crypto.randomBytes(32));
}

function generateCodeChallenge(verifier: string): string {
  return base64URLEncode(crypto.createHash("sha256").update(verifier).digest());
}

async function authenticate() {
  const msalApp = new PublicClientApplication({
    auth: {
      clientId: CLIENT_ID,
      authority: `https://login.microsoftonline.com/${TENANT_ID}`,
    },
    cache: { cachePlugin },
  });

  const codeVerifier = generateCodeVerifier();
  const codeChallenge = generateCodeChallenge(codeVerifier);

  const authUrl = await msalApp.getAuthCodeUrl({
    scopes: GRAPH_SCOPES,
    redirectUri: REDIRECT_URI,
    codeChallenge,
    codeChallengeMethod: "S256",
  });

  console.log("\nMicrosoft 365 — Autenticación\n");
  console.log("Abriendo navegador para login...\n");
  exec(`open "${authUrl}"`);
  console.log("Si el navegador no se abre, ve manualmente a:\n");
  console.log(authUrl + "\n");
  console.log("Esperando que completes el login en el navegador...\n");

  const code = await new Promise<string>((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const rawUrl = req.url ?? "/";
      const url = new URL(rawUrl, REDIRECT_URI);
      const code = url.searchParams.get("code");
      const error = url.searchParams.get("error");
      const errorDesc = url.searchParams.get("error_description");

      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(`<html><body style="font-family:sans-serif;padding:40px;text-align:center">
        <h2 style="color:#0078d4">Autenticación completada</h2>
        <p>Puedes cerrar esta pestaña y volver al terminal.</p>
      </body></html>`);

      server.close();

      if (code) {
        resolve(code);
      } else {
        reject(new Error(errorDesc ?? error ?? "No se recibió código de autorización"));
      }
    });

    server.listen(3000, () => {
      console.log("Servidor local escuchando en http://localhost:3000\n");
    });

    setTimeout(() => {
      server.close();
      reject(new Error("Timeout: el login tardó más de 5 minutos"));
    }, 300000);
  });

  const result = await msalApp.acquireTokenByCode({
    code,
    scopes: GRAPH_SCOPES,
    redirectUri: REDIRECT_URI,
    codeVerifier,
  });

  if (result) {
    console.log("Autenticación exitosa!");
    console.log(`  Cuenta : ${result.account?.username}`);
    console.log(`  Token  : ${TOKEN_CACHE_PATH}`);
    console.log("\nEl servidor MCP está listo. Reinicia Claude Code.\n");
  }
}

authenticate().catch((err) => {
  console.error("\nError de autenticación:", err.message);
  process.exit(1);
});

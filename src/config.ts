import * as os from "os";
import * as path from "path";

// Todos los procesos comparten caché, aunque el cliente MCP cambie el CWD.
// La configuración relativa de .env siempre se interpreta desde el proyecto.
export function resolveTokenCachePath(
  configuredPath: string | undefined = process.env.TOKEN_CACHE_PATH,
  projectRoot: string = path.resolve(__dirname, ".."),
  homeDir: string = os.homedir(),
): string {
  const cachePath = configuredPath?.trim();
  return cachePath
    ? path.resolve(projectRoot, cachePath)
    : path.join(homeDir, ".m365-mcp", ".token_cache.json");
}

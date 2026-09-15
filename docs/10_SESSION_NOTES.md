# Notas de sesión

## 2026-09-16 — Claude Code (Mac) — Revisión del trabajo de DeepSeek + endurecimiento

### Hecho
- Reconciliado con `origin/main` (`542776d`, HP): los scripts env-sync del HP son los canónicos; las copias locales de DeepSeek (sin trackear, distintas) se apartaron. `cred-store.sh` apunta a la entrada de Keychain que ya existía en el Mac (servicio `com.luisfran.m365-mcp-server`, cuenta `bw-session-env-sync`). Scripts con `+x`.
- 🔒 Token del bot: `sanitize_url` no lo enmascaraba (el `:` del token rompía la regex) y salía en claro en `dist/bot.log` en cada error de red (68 líneas del 13 al 15/09, ya redactadas). Ahora `log()` redacta siempre.
- Responder por lenguaje natural pide confirmación (`confirm_reply`); antes enviaba directamente lo que interpretaba el LLM.
- El log de lenguaje natural ya no guarda el texto ni los params (llevaban destinatarios y cuerpos).
- Avisos push con id corto propio (`a1`, `a2`…) vía `register_alert`: ya no sustituyen la última lista de `/hoy` o `/buscar`.
- `_read_token_from_cache` sin fallback a un token de otro scope.
- LLM por defecto: alias `local-fast` vía LiteLLM (`:4000`) en código y `.env`; `qwen/qwen3.8-27b` salió del stack (bloqueaba el arranque de opencode).
- `taxonomy.json` a `.gitignore` (contiene nombres de personas).
- Tests: +7 con rojo visto → verdes. Ejecutar con `cd test && python3 -m unittest test_bot` (desde la raíz, `-m unittest test.test_bot` choca con el paquete `test` de la stdlib).
- Auto-clasificación (decisión del operador, mismo día): keywords como palabra completa (antes `agua` casaba «paraguas» y `cargo` «encargo»); por defecto **propone** con botón Aplicar y no repite la misma propuesta en cada intervalo (`auto_classify_tick`); `TELEGRAM_AUTO_CLASSIFY_APPLY=true` recupera el mover sin confirmar. +4 tests con rojo visto.

### Pendiente
- Los nombres de personas siguen en el fallback hardcodeado de `load_taxonomy()` (ya estaban commiteados antes de esta sesión).

### Decidido
- Todo cliente de LLM local va por alias de LiteLLM, nunca contra un modelo fijo de LM Studio.

## 2026-09-15 — DeepSeek — Optimización y lenguaje natural

### Hecho
- **Bugfix**: `sender` → `from` en `fetch_unread` y `classify_unread` (estándar Graph API)
- **taxonomy.json**: reglas de clasificación externalizadas, editables sin tocar código. Hot-reload por mtime + comando `/reload`
- **Optimizaciones de rendimiento**:
  - Token caching en Python puro (`_read_token_from_cache()`): 44ms → <1ms (847x)
  - Folder ID cache persistido (`_folder_cache.json`): evita caminar árbol de Outlook repetido
  - Keyword index O(1) con early break: `_keyword_index` plano en lugar de bucle anidado
- **Auto-clasificación**: `TELEGRAM_AUTO_CLASSIFY_INTERVAL=600` en `.env`. El bot clasifica solo cada 10 min
- **`/stats`**: nuevo comando con métricas (clasificaciones, movidos, fallidos, llamadas API, uptime)
- **Indicador de adjuntos** (📎) en `/hoy`
- **Reintento inteligente**: si `/aplicar` falla por 401, refresca token y reintenta
- **Reglas condicionales** en taxonomy.json: `if_sender`, `if_subject_contains` (AND con keywords)
- **Notificaciones push con botones inline**: Leído/Archivar/Eliminar/Responder directo en la notificación
- **Lenguaje natural**: LLM local (Qwen3-8B vía LM Studio) interpreta mensajes sin `/`. Coste cero.
  - Config: `TELEGRAM_LLM_ENABLED=true`, modelo `qwen/qwen3.8-27b` (corregido 16/09: ahora alias `local-fast` vía LiteLLM)
  - Primer mensaje tarda ~20s (warm-up), siguientes ~2-3s
  - Si falla, muestra aviso y sugiere comandos con `/`

### Pendiente
- Nada urgente. El bot está completo y funcionando.

### Decidido
- LLM local para lenguaje natural (no cloud, datos sensibles no salen del Mac)

## 2026-08-08 — Codex — Gestión segura de OneDrive

### Hecho
- Añadidas las herramientas MCP `list_onedrive_folder`, `get_onedrive_item_metadata`, `create_onedrive_folder` y `move_onedrive_item` en `src/index.ts` y `src/onedrive.ts`.
- Añadidas pruebas unitarias y de contrato MCP en `test/`; 13 pruebas y compilación en verde.
- Instalados localmente los gates pre-commit de Conclave y RGPD en `.git/hooks/`.

### Pendiente
- Reiniciar la conexión MCP de Codex/Claude para que el cliente descubra las cuatro herramientas nuevas.
- Hacer una primera lectura real del OneDrive y organizar por lotes pequeños antes de ampliar el alcance.
- Commit pendiente: `.gitignore` contenía cambios previos del operador y no se mezclaron en un commit automático.

### Decidido
- Los movimientos exigen ID, nombre y carpeta de origen esperados; cualquier cambio desde el inventario aborta la operación.
- La creación y el movimiento fallan ante conflictos; no renombran ni sustituyen silenciosamente.
- El listado pagina internamente hasta 1.000 elementos por llamada y permite continuar mediante una URL validada de Microsoft Graph.

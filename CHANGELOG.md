# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) · versionado semántico.

## [1.1.0] — 2026-10-21

### Seguridad
- `M365_READ_ONLY=1` bloquea toda escritura; `M365_CONFIRM_WRITES=1` exige `"confirm": true`.
  Clasificación por acción real (list ≠ create) y fail-closed para herramientas nuevas.
- `M365_MINIMAL_SCOPES=1`: login con los permisos que el servidor usa de verdad, sin
  `Mail.ReadWrite`, `Sites.ReadWrite.All`, `Chat.ReadWrite`, `Contacts`, `Notes`,
  `OnlineMeetings`, `MailboxSettings`. Por defecto no cambia (no invalida sesiones).
- `auth.ts` abre el navegador con `spawn(argv)` en vez de `exec("open \"…\"")`:
  la URL de autorización ya no pasa por una shell.
- Los scopes de `auth.ts` y del bot salen de una sola fuente (`src/policy.ts`).

### Arreglado
- Reintentos de Graph: `429`/`503`/`504` se reintentan con backoff y `Retry-After`,
  **salvo `POST`** (enviar correo o crear evento no son idempotentes: un reintento
  duplicaría el envío). Cadena del SDK montada en `src/graph.ts`, con test.
- Cliente de Graph construido sin `AmbiguityInInitialization` (el SDK no admite
  `authProvider` y `middleware` a la vez); test de regresión que sí instancia el cliente.
- Mensajes de Telegram > 4096 caracteres se trocean (antes fallaban); `/ver` ya no
  corta el cuerpo a 1500 caracteres. El troceo mide unidades UTF-16 (los emoji cuentan
  2), corta solo por saltos de línea para no romper Markdown y registra en el log
  cualquier trozo que no se entregue.

### Añadido
- El bot respeta `M365_READ_ONLY=1`: bloquea enviar, responder, marcar, archivar, borrar y
  aplicar el plan, con aviso explícito; leer/buscar/ver siguen funcionando.
  `test/test_politicas_bot.py` (5 tests).
- Rotación de `dist/bot.log` a 5 MB (una copia `.1`): en una instalación llegó a 2,7 GB.
- `src/policy.ts` (sin efectos, testeable) y `test/policy.test.mjs` (8 tests).
- `test/test_fragmentos.py` (9 tests) para el troceo.
- `README.en.md` completo y este CHANGELOG.

### Documentado
- `M365_READ_ONLY` y `M365_MINIMAL_SCOPES` aplican **también al bot de Telegram**;
  `M365_CONFIRM_WRITES` es solo del servidor MCP (el bot ya confirma por botones).
- Rotación del log del bot: 5 MB y una sola copia `.1`.
- Límites reales: monousuario, sin aislamiento entre usuarios, disponibilidad según
  tipo de cuenta y permisos de Microsoft.

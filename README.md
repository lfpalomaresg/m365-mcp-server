# M365 Personal Suite — MCP Server + Telegram Bot

Servidor MCP local en TypeScript para trabajar con Microsoft 365 mediante Microsoft Graph. Expone herramientas de Outlook, OneDrive, Excel, calendario y tareas a un cliente MCP por `stdio`. Incluye un bot de Telegram opcional, escrito con la biblioteca estándar de Python.

**English:** A local Microsoft Graph MCP server with 13 tools and an optional Telegram mail bot. Built for personal workflows; see setup, permissions and testing limits below.

El proyecto nació para uso propio con Claude Code. La configuración de ese cliente se documenta abajo; la compatibilidad con otros clientes MCP y la adopción externa no están acreditadas aquí. Es software independiente, sin afiliación con Microsoft, Anthropic ni Telegram.

## Herramientas MCP

| Herramienta | Función | Efecto |
|---|---|---|
| `search_onedrive_files` | Buscar archivos | Lectura remota |
| `list_onedrive_folder` | Listar una carpeta por ID, con paginación | Lectura remota |
| `get_onedrive_item_metadata` | Consultar metadatos por ID | Lectura remota |
| `create_onedrive_folder` | Crear una carpeta | Escritura remota |
| `move_onedrive_item` | Mover un elemento comprobando nombre y padre esperados | Escritura remota |
| `download_onedrive_file` | Devolver texto o guardar un binario | Lectura remota; posible escritura local |
| `upload_onedrive_file` | Crear o sobrescribir un archivo de texto | Escritura remota |
| `update_excel_sheet` | Leer o escribir rangos de un libro | Lectura o escritura remota |
| `get_latest_emails` | Consultar correos recientes con filtros | Lectura remota |
| `send_outlook_email` | Enviar un correo, con HTML y CC opcionales | Envío inmediato |
| `download_email_attachments` | Guardar adjuntos de un mensaje | Lectura remota y escritura local |
| `manage_todo_tasks` | Listar, crear o completar tareas | Lectura o escritura remota |
| `sync_calendar_events` | Listar o crear eventos | Lectura o escritura remota; puede enviar invitaciones |

Las herramientas con escritura ejecutan la operación al invocarse. Para reducirlo hay tres
políticas opcionales (en `.env`, ver `.env.example`):

| Variable | Efecto |
|---|---|
| `M365_READ_ONLY=1` | Bloquea **todas** las escrituras; las lecturas siguen funcionando |
| `M365_CONFIRM_WRITES=1` | Cada escritura exige `"confirm": true` en la llamada (dos pasos) |
| `M365_MINIMAL_SCOPES=1` | El login pide solo los permisos que el servidor usa (requiere reautenticar) |

El servidor reintenta los `429`/`503`/`504` de Graph (3 intentos, respeta `Retry-After`)
**salvo en `POST`**, que no es idempotente: reintentar `sendMail` podría enviar el correo dos
veces. Los mensajes de Telegram de más de 4096 caracteres se trocean (midiendo en unidades
UTF-16, que es como los cuenta Telegram).

Estas políticas aplican **solo al servidor MCP**; el bot de Telegram tiene su propio flujo de
confirmación y no las lee.

## Requisitos y alcance

- Git, npm y Node.js. La integración continua usa **Node.js 22**.
- Python para el bot o las pruebas. La integración continua usa **Python 3.11**; las pruebas necesitan `pytest`.
- Una cuenta de Microsoft y una aplicación registrada en Microsoft Entra/Azure, con los permisos delegados necesarios.
- Un cliente MCP con transporte `stdio`; la configuración de ejemplo es para Claude Code.

La disponibilidad de cada API depende del tipo de cuenta, los permisos y las políticas de Microsoft. No se garantiza que todas las herramientas funcionen con todas las cuentas personales o corporativas. El proyecto no ofrece un servicio alojado ni aislamiento entre varios usuarios.

## Instalación desde código

```bash
git clone https://github.com/lfpalomaresg/m365-mcp-server.git
cd m365-mcp-server
npm ci
npm run build
```

`npm ci` utiliza `package-lock.json`. La compilación genera `dist/`; no inicia sesión ni conecta con un buzón.

### Configuración local

1. Copia `.env.example` a `.env` **solo si todavía no existe** y edítalo localmente.
2. Introduce el `CLIENT_ID` de tu aplicación y el `TENANT_ID` correspondiente. El valor `common` permite solicitar acceso a distintos tipos de cuenta, sujeto a la configuración de la aplicación y a Microsoft.
3. Configura el caché y una ruta absoluta para las descargas.

Ejemplo para macOS; sustituye `tu-usuario` y el identificador de aplicación:

```env
CLIENT_ID=identificador-de-tu-aplicacion
TENANT_ID=common
TOKEN_CACHE_PATH=.token_cache.json
DOWNLOAD_PATH=/Users/tu-usuario/Downloads/m365-mcp
```

En Linux, utiliza la ruta absoluta de tu directorio personal para las descargas. En Windows, por ejemplo, `C:/Users/tu-usuario/Downloads/m365-mcp`. No uses `~` como abreviatura dentro de `.env`.

El servidor, la autenticación y el bot comparten la resolución de `TOKEN_CACHE_PATH`: una ruta absoluta se conserva; una relativa se resuelve desde la raíz del proyecto. Si se omite, usan `~/.m365-mcp/.token_cache.json` mediante el directorio personal del sistema. Para conservar un caché histórico situado en la raíz del proyecto, declara explícitamente `TOKEN_CACHE_PATH=.token_cache.json`.

### Registro de aplicación y autenticación

Registra `http://localhost:3000` como URI de redirección para una aplicación de escritorio/cliente público. Selecciona los tipos de cuenta que correspondan a tu uso. La lista exacta de permisos solicitados está en `GRAPH_SCOPES` de [`src/auth.ts`](src/auth.ts); revísala antes de conceder acceso. El inicio de sesión solicita actualmente más permisos que los utilizados por el servidor MCP.

Cuando estés preparado para conectar tu cuenta, ejecuta tú mismo:

```bash
npm run auth
```

Completa el inicio de sesión y el consentimiento en la interfaz oficial de Microsoft. El comando intenta abrir el navegador con `open` de macOS; en Windows/Linux puede ser necesario abrir manualmente la URL que muestra **en tu propio navegador**. No compartas esa URL, códigos de autorización ni archivos de caché. El puerto local 3000 debe estar disponible.

`scripts/setup.py` es un asistente alternativo de configuración; su comprobación de credenciales no sustituye el paso `npm run auth` que guarda el caché usado por el servidor.

### Cliente MCP

Integra esta entrada en la configuración MCP de Claude Code, conservando cualquier configuración existente:

```json
{
  "mcpServers": {
    "m365-personal-suite": {
      "command": "node",
      "args": ["/ruta/absoluta/al/proyecto/dist/index.js"]
    }
  }
}
```

Reinicia el cliente después de modificar la configuración. Empieza con una consulta de lectura, por ejemplo «Lista las carpetas de mi OneDrive». `npm start` ejecuta el servidor por `stdio`; no abre una interfaz web.

## Bot de Telegram opcional

Añade a `.env` el token de tu bot y tu ID numérico autorizado. Para empezar solo con comandos, desactiva la interpretación mediante un modelo:

```env
TELEGRAM_BOT_TOKEN=token-de-tu-bot
TELEGRAM_ALLOWED_USER_ID=tu-id-numerico
TELEGRAM_LLM_ENABLED=false
TELEGRAM_AUTO_CLASSIFY_INTERVAL=0
TELEGRAM_AUTO_CLASSIFY_APPLY=false
```

```bash
python telegram_bot.py
```

Comandos principales: `/hoy`, `/buscar <texto>`, `/ver <nº>`, `/calendario`, `/tareas`, `/adjuntos <nº>`, `/clasifica`, `/aplicar`, `/enviar` y `/responder <nº> <texto>`. Los botones también permiten marcar, archivar y eliminar mensajes. Revisa las reglas de clasificación antes de aplicarlas a un buzón real.

El bot transmite a Telegram el contenido que consulta y muestra. Si activas la interpretación de lenguaje natural, enviará tus instrucciones al endpoint `TELEGRAM_LLM_URL` (por defecto, un servicio local en `http://localhost:4000/v1/chat/completions`). El modelo y el servicio no vienen incluidos. El bot no instala paquetes Python externos, pero utiliza el componente Node compilado para renovar la sesión de Microsoft cuando es necesario.

## Privacidad y almacenamiento

- `.env` y el caché de autenticación contienen información sensible; no los publiques ni los adjuntes a incidencias.
- El caché se guarda como archivo local, no como una bóveda cifrada. El código aplica permisos POSIX restrictivos; revisa además los permisos de acceso de tu sistema operativo.
- Las descargas del servidor van a `DOWNLOAD_PATH` o al destino indicado en la herramienta. Revisa qué archivos guardas y quién puede acceder a ellos.
- El bot guarda estado, planes de clasificación, logs y adjuntos bajo `dist/`. Parte del estado puede contener destinatarios, asuntos o identificadores de mensajes. La redacción de tokens en logs no elimina todos los datos personales.
- El cliente MCP recibe el contenido devuelto por las herramientas; su tratamiento posterior depende del cliente y del proveedor de modelo que hayas elegido.

## Pruebas sin cuentas reales

La CI compila TypeScript y ejecuta pruebas Node/Python con valores ficticios y servicios simulados. Comprueba validaciones, operaciones OneDrive simuladas, caché, contrato MCP, bot y asistente de configuración. **No acredita una autenticación real ni una operación completa contra Microsoft Graph o Telegram.**

Para reproducirla, usa un clon separado **sin `.env`** ni cachés reales. Tras `npm ci`, crea un entorno Python y actívalo con el comando de tu sistema:

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install pytest
python -c "from pathlib import Path; Path('.env').open('x').write('CLIENT_ID=ci-dummy-client-id\nTELEGRAM_BOT_TOKEN=000000:ci-dummy-token\nTELEGRAM_ALLOWED_USER_ID=1\n')"
npm test
```

La creación con modo `x` falla si ya existe `.env`, para no sobrescribir una configuración. Si tu sistema solo ofrece `python3`, úsalo para crear el entorno; una vez activado, el script de pruebas espera `python` en `PATH`. El archivo ficticio permite importar el bot y arrancar el servidor MCP para consultar su lista de herramientas; no sirve para iniciar sesión.

## Resolución de problemas

- **`No active session found`:** verifica que `TOKEN_CACHE_PATH` identifique el archivo generado por `npm run auth`. Si la sesión ha caducado o fue revocada, vuelve a autenticarte tú mismo y reinicia el cliente. No compartas el contenido del caché para diagnosticarlo.
- **Error de permisos o API:** comprueba el tipo de cuenta, el consentimiento y la disponibilidad del endpoint de Microsoft Graph. Una compilación correcta no demuestra acceso a ese servicio.
- **Bot sin sesión:** confirma que el caché está en la ubicación configurada y que existe `dist/token.js` después de compilar.
- **Pruebas que no arrancan:** confirma que el entorno Python está activo, tiene `pytest` y existe el `.env` ficticio en el clon de pruebas.

## Contribuir

Puedes abrir una incidencia o proponer una mejora con instrucciones de reproducción y datos ficticios. Indica sistema operativo, versiones de Node/Python y resultado esperado. No adjuntes correos reales, tokens, cachés, `.env`, documentos privados ni URLs de autenticación. Los cambios en operaciones con escritura deben incluir pruebas que no actúen sobre cuentas reales.

## Licencia

[MIT](LICENSE). Copyright © 2026 Luis Francisco Palomares Gamarra. Las dependencias conservan sus propias licencias.

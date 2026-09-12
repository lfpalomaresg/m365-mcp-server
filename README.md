# M365 Personal Suite — MCP Server + Telegram Bot

Servidor MCP local que conecta tu cuenta personal de **Microsoft 365** a **Claude Code** mediante la API de Microsoft Graph, más un **bot de Telegram** (`telegram_bot.py`) para gestionar el correo desde el móvil. Sin dependencias externas en el bot (stdlib puro de Python).

---

## Herramientas del servidor MCP (13 tools)

### OneDrive & Excel
| Tool | Descripción |
|------|-------------|
| `search_onedrive_files` | Buscar archivos por nombre, extensión o palabra clave |
| `list_onedrive_folder` | Listar carpetas de OneDrive |
| `get_onedrive_item_metadata` | Metadatos de un archivo/carpeta |
| `create_onedrive_folder` | Crear carpeta |
| `move_onedrive_item` | Mover archivo/carpeta por ID estable |
| `download_onedrive_file` | Leer contenido de archivos texto/JSON/CSV o descargar binarios |
| `upload_onedrive_file` | Crear o sobrescribir archivos en OneDrive |
| `update_excel_sheet` | Leer o escribir celdas y rangos en libros Excel |

### Outlook
| Tool | Descripción |
|------|-------------|
| `get_latest_emails` | Recuperar correos recientes con filtros opcionales |
| `send_outlook_email` | Enviar correos con soporte HTML y CC |
| `download_email_attachments` | Descargar adjuntos de un correo a local |

### Calendario & Tareas
| Tool | Descripción |
|------|-------------|
| `manage_todo_tasks` | Listar, crear y completar tareas en Microsoft To-Do |
| `sync_calendar_events` | Listar eventos o crear nuevas reuniones |

---

## Bot de Telegram

Bot conversacional para gestionar el correo desde el móvil (Windows/Mac/móvil, independiente de las apps de escritorio).

```bash
npm run bot   # arranca telegram_bot.py en modo polling
```

| Comando | Descripción |
|---------|-------------|
| `/hoy` | Correos sin leer recibidos hoy |
| `/clasifica` | Propone mover correos por taxonomía de carpetas |
| `/aplicar` | Ejecuta la clasificación propuesta |
| `/buscar <texto>` | Búsqueda full-text en el buzón |
| `/ver <nº>` | Lee el cuerpo completo de un correo |
| `/enviar` | Enviar un correo paso a paso (destinatario → asunto → cuerpo) |
| `/responder <nº> <texto>` | Responde a un correo |
| `/calendario` | Eventos de hoy |
| `/tareas` | Tareas pendientes de To-Do |
| `/adjuntos <nº>` | Descarga adjuntos a `dist/attachments/` |

Además de comandos, el bot muestra **botones inline** (`Hoy`, `Clasificar`, `Buscar`, `Enviar`, `Calendario`, `Tareas`) y **botones de acción** por correo (`Leído`, `Archivar`, `Eliminar`, `Responder`).

### Configuración del bot (.env)

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ALLOWED_USER_ID=123456789
# Opcional — notificaciones push de remitentes importantes
TELEGRAM_IMPORTANT_SENDERS=jefe@empresa.com,contabilidad
TELEGRAM_NOTIFY_INTERVAL=120
```

### Estado y logs

- Conversaciones en curso → `dist/_bot_state.json` (persisten reinicios)
- Logs → `dist/bot.log`
- Plan de clasificación → `dist/_bot_plan.json`
- Adjuntos descargados → `dist/attachments/`

---

## Requisitos

- Node.js v18+
- Python 3.8+ (para el bot, solo stdlib)
- Cuenta Microsoft 365 personal (Outlook, OneDrive, etc.)
- App Registration en Azure con soporte para cuentas personales
- Claude Code CLI

---

## Instalación

```bash
# 1. Clonar e instalar dependencias
git clone https://github.com/lfpalomaresg/m365-mcp-server.git
cd m365-mcp-server
npm install

# 2. Configurar credenciales
cp .env.example .env
# Editar .env con tu CLIENT_ID de Azure

# 3. Compilar
npm run build

# 4. Autenticación (solo la primera vez)
npm run auth
# Abre el navegador → login con cuenta Microsoft personal → listo

# 5. Registrar en Claude Code
# El servidor se registra automáticamente si sigues la guía de setup
```

---

## Configuración del entorno (.env)

```env
CLIENT_ID=tu-client-id-de-azure
TENANT_ID=common
TOKEN_CACHE_PATH=.token_cache.json
DOWNLOAD_PATH=/ruta/local/para/descargas
```

> **Nunca compartas ni subas al repositorio:** `.env` ni `.token_cache.json`

---

## Configuración de Azure App Registration

La app debe estar registrada con:
- **Supported account types:** Multitenant + cuentas Microsoft personales
- **Plataforma:** Aplicaciones móviles y de escritorio
- **Redirect URI:** `http://localhost:3000`
- **Allow public client flows:** Yes (en Authentication → Advanced settings)
- **Permisos delegados:** Ver lista completa en `PROMPT.md`

---

## Registro en Claude Code

Añadir en `~/.claude.json`:

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

---

## Uso con Claude Code

Una vez registrado y autenticado, habla con Claude directamente:

```
"Muéstrame mis últimos 10 correos no leídos"
"Busca archivos Excel en mi OneDrive del mes pasado"
"Crea una tarea en To-Do: revisar propuesta para el viernes"
"Envía un email a juan@empresa.com con el asunto 'Reunión'"
"¿Qué eventos tengo esta semana en el calendario?"
```

---

## Scripts disponibles

```bash
npm run build   # Compilar TypeScript
npm run test    # Tests MCP (JS) + bot (Python)
npm run auth    # Autenticacion inicial (PKCE flow)
npm start       # Arrancar servidor MCP manualmente
npm run bot     # Arrancar el bot de Telegram
```

---

## Troubleshooting

### `Error: No active session found. Run 'npm run auth'...`

El server **no encuentra un token válido**. Dos causas posibles:

**1. La sesión ha caducado** (refresh token expirado o revocado). Vuelve a autenticarte:

```bash
cd /ruta/al/proyecto
npm run auth      # completa el login en el navegador
```

Después **reinicia Claude Code** (o el proceso del server MCP) para que recargue la sesión.

**2. El server busca el token en el directorio equivocado** 🐛 *(bug histórico — ya corregido)*

Claude Code lanza el server MCP desde un **CWD arbitrario** (normalmente el `$HOME` del usuario), **no** desde la carpeta del proyecto. Si `TOKEN_CACHE_PATH` en `.env` es una **ruta relativa** (`.token_cache.json`), el server la resuelve contra ese CWD y nunca encuentra el token que escribió `npm run auth` (que sí corre desde el proyecto). Resultado: **`npm run auth` funciona, pero el server siempre responde *"No active session found"*.**

**Solución aplicada:**
- El código (`src/index.ts` y `src/auth.ts`) ahora resuelve cualquier ruta relativa de `TOKEN_CACHE_PATH` contra la **raíz del proyecto**, no contra el CWD.
- Además se recomienda usar **ruta absoluta** en `.env`:

```env
TOKEN_CACHE_PATH=/Users/tu-usuario/ruta/al/proyecto/.token_cache.json
```

> 💡 **Diagnóstico rápido:** si `npm run auth` termina con éxito pero el server sigue fallando, casi seguro es este problema de ruta/CWD. Comprueba dónde está realmente el `.token_cache.json` y desde qué directorio se lanza el server (`args` en `~/.claude.json`).

### Verificar la sesión sin pasar por Claude

```bash
node -e 'require("dotenv").config({path:".env"});const{PublicClientApplication}=require("@azure/msal-node");const fs=require("fs");const P=process.env.TOKEN_CACHE_PATH;const cp={beforeCacheAccess:async c=>{if(fs.existsSync(P))c.tokenCache.deserialize(fs.readFileSync(P,"utf-8"))},afterCacheAccess:async()=>{}};(async()=>{const a=new PublicClientApplication({auth:{clientId:process.env.CLIENT_ID,authority:`https://login.microsoftonline.com/${process.env.TENANT_ID}`},cache:{cachePlugin:cp}});const acc=await a.getTokenCache().getAllAccounts();console.log("Cuentas:",acc.map(x=>x.username));})()'
```

Si imprime tu cuenta, la sesión es válida y el problema está en la ruta/CWD del server.

---

## Estructura del proyecto

```
m365-mcp-server/
├── src/
│   ├── index.ts      # Servidor MCP principal (9 tools)
│   └── auth.ts       # Script de autenticación PKCE
├── dist/             # Código compilado (generado)
├── .env.example      # Plantilla de configuración
├── .gitignore
├── package.json
├── tsconfig.json
├── PROMPT.md         # Prompts y arquitectura del proyecto
└── README.md
```

---

## Tecnologías

- [@modelcontextprotocol/sdk](https://github.com/modelcontextprotocol/typescript-sdk)
- [@azure/msal-node](https://github.com/AzureAD/microsoft-authentication-library-for-js)
- [@microsoft/microsoft-graph-client](https://github.com/microsoftgraph/msgraph-sdk-javascript)

---

## Licencia

MIT

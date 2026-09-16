# M365 MCP Server — Material de consultoría

> Cómo se construyó, cómo extenderlo, cómo desplegarlo en un cliente nuevo.
> Para consultores técnicos y clientes con perfil de IT.

---

## 1. Arquitectura

```
┌─────────────────────────────────────────────────┐
│ Claude Code / Opencode (host)                   │
│  ├─ MCP Server (Node/TypeScript, stdio)         │
│  │   ├─ Auth: MSAL PKCE (Azure AD)              │
│  │   ├─ API: Microsoft Graph (13 herramientas)  │
│  │   └─ Cache: token en disco (~/.m365-mcp/)   │
│  └─ Bot Telegram (Python 3, stdlib only)        │
│      ├─ Clasificación de correos (taxonomy)     │
│      ├─ Comandos (/hoy, /clasifica, /buscar)    │
│      └─ Auto-clasificación periódica            │
└─────────────────────────────────────────────────┘
```

### Componentes

| Componente | Lenguaje | Dependencias | Rol |
|---|---|---|---|
| MCP Server | TypeScript | MSAL, Graph SDK, MCP SDK | Conexión Claude↔M365 |
| Telegram Bot | Python 3 | **Cero** (stdlib) | Gestión móvil de correo |
| taxonomy.json | JSON | — | Reglas de clasificación editables |

---

## 2. Stack y decisiones clave

### Por qué MSAL PKCE
- **Sin secretos en cliente**: el flujo PKCE (Proof Key for Code Exchange) no requiere client secret. Solo necesita CLIENT_ID.
- **Multi-tenant**: con `TENANT_ID=common`, funciona con cuentas personales y corporativas.
- **Sin servidor intermedio**: el token se obtiene directamente del dispositivo.

### Por qué Microsoft Graph SDK
- Tipado completo en TypeScript.
- Manejo automático de refresh tokens.
- Paginación nativa (`@microsoft/microsoft-graph-client`).

### Por qué bot en Python stdlib
- **Cero instalación**: `python3 telegram_bot.py` y funciona. Sin pip, sin venv.
- **Token cache en Python puro**: lectura del MSAL cache file sin depender de `@azure/msal-node`.
- **Hot-reload de taxonomy**: cambios en `taxonomy.json` se detectan por mtime, sin reiniciar.

### Por qué taxonomy.json externo
- La clasificación de correos la configura el cliente, no el desarrollador.
- Formato JSON simple: `{rules: [{folder, keywords, if_sender?, if_subject_contains?}]}`.
- Soporta reglas condicionales (AND de sender + subject + keywords).
- Hot-reload sin reiniciar el bot.

---

## 3. Flujo de autenticación (PKCE)

```
Cliente                    Azure AD                  Graph API
  │                           │                         │
  │  1. POST /authorize       │                         │
  │──────────────────────────►│                         │
  │  2. Usuario inicia sesión │                         │
  │◄──────────────────────────│                         │
  │  3. Redirect con code     │                         │
  │◄──────────────────────────│                         │
  │  4. POST /token (code)    │                         │
  │──────────────────────────►│                         │
  │  5. access_token +        │                         │
  │     refresh_token         │                         │
  │◄──────────────────────────│                         │
  │  6. Cache a disco         │                         │
  │                           │  7. GET /me/messages    │
  │                           │◄────────────────────────│
  │                           │  8. 200 OK              │
  │                           │────────────────────────►│
```

`npm run auth` hace el flujo completo y guarda el token (paso 6); el MCP server lo renueva solo. `scripts/setup.py` solo **verifica** el CLIENT_ID con los pasos 1-5 y genera el `.env`: el token que obtiene no se guarda.

---

## 4. Cómo extenderlo

### Añadir una herramienta MCP

1. En `src/index.ts`, añade la definición en el array `tools`:
```typescript
{
  name: "mi_nueva_tool",
  description: "Descripción para Claude",
  inputSchema: { type: "object", properties: { ... } }
}
```

2. Añade el handler en el bloque `server.setRequestHandler(CallToolRequestSchema, ...)`:
```typescript
case "mi_nueva_tool":
  // Llamar a Graph API
  break;
```

3. Recompila: `npm run build`

### Añadir una regla de clasificación

Edita `taxonomy.json`:
```json
{
  "rules": [
    {
      "folder": "Carpeta/Destino",
      "keywords": ["palabra1", "palabra2"],
      "if_sender": "remitente@email.com",
      "if_subject_contains": "texto en asunto"
    }
  ]
}
```

- `keywords`: **palabra completa** (no subcadena). "cargo" no casa "encargo".
- `if_sender`: opcional, filtra por nombre o email del remitente.
- `if_subject_contains`: opcional, texto que debe aparecer en el asunto.
- Las condiciones son **AND**: se deben cumplir todas (si están presentes).
- Sin condiciones = solo keywords, indexadas para O(1).

El bot recarga automáticamente. También puedes forzar con `/reload`.

### Añadir un comando al bot

En `telegram_bot.py`, añade un handler en la función `handle_update()`:
```python
if text.startswith("/mi_comando"):
    # Lógica
    send_message(chat_id, "resultado")
```

---

## 5. Despliegue en un cliente nuevo

### Requisitos previos
- Azure App Registration con redirect URI **`http://localhost:3000`** (el que usa `src/auth.ts`). ⚠️ `scripts/setup.py` verifica hoy contra `http://localhost`: hasta que se alinee, registra ambos o la verificación fallará.
- Permisos de API delegados: los **16** de `GRAPH_SCOPES` en `src/auth.ts` (ver §7).
- Node.js 22+, Python 3.10+

### Paso a paso (2 minutos con setup.py)

```bash
git clone https://github.com/lfpalomaresg/m365-mcp-server.git
cd m365-mcp-server
npm install
python scripts/setup.py     # Pide CLIENT_ID, lo verifica y crea .env (⚠️ SOBRESCRIBE un .env existente)
npm run build
npm run auth                 # Login real y guardado del token
npm start                    # Arranca el MCP server
```

### Configurar en Claude Code / Opencode

Añadir al `claude_desktop_config.json` o `opencode.json`:
```json
{
  "mcpServers": {
    "m365-personal-suite": {
      "command": "node",
      "args": ["/ruta/al/proyecto/dist/index.js"],
      "env": {
        "CLIENT_ID": "<id>",
        "TENANT_ID": "common",
        "TOKEN_CACHE_PATH": "/ruta/al/proyecto/.token_cache.json"
      }
    }
  }
}
```

### Activar el bot de Telegram (opcional)

1. Crear bot con [@BotFather](https://t.me/BotFather)
2. Obtener tu chat ID con [@userinfobot](https://t.me/userinfobot)
3. Añadir al `.env`:
```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ALLOWED_USER_ID=123456789
```
4. Arrancar: `python telegram_bot.py`

### Configurar como servicio (Mac)
```bash
# LaunchAgent para arranque automático
# Ver ~/Library/LaunchAgents/com.luisfran.m365-telegram-bot.plist como ejemplo
```

### Configurar como servicio (Windows)
```powershell
# Programador de tareas o NSSM
nssm install M365Bot python telegram_bot.py
```

---

## 6. Mantenimiento

### Actualizar
```bash
git pull
npm install        # Si cambiaron dependencias
npm run build      # Recompilar TypeScript
# El bot recarga taxonomy automáticamente
```

### Monitorizar
- **MCP Server**: logs vía stderr del proceso MCP
- **Bot Telegram**: `dist/bot.log` (sanitizado, sin tokens ni cuerpos de email)
- **LaunchAgent**: `~/Library/Logs/m365-telegram-bot.*.log`

### Tokens
- El access token se renueva automáticamente vía refresh token
- El refresh token vive en `~/.m365-mcp/.token_cache.json`
- Caducidad típica: 90 días (Microsoft). Si expira, re-ejecutar `npm run auth`.

---

## 7. FAQ de cliente

**¿Mis datos salen de mi ordenador?**
El MCP server corre en local y los tokens de Microsoft se guardan solo en tu disco: el desarrollador no tiene acceso a tu cuenta. Pero **sí salen datos**, y conviene decirlo claro:
- Lo que devuelven las herramientas (correos, ficheros, eventos que el asistente consulta) se envía al **proveedor del modelo de IA** que use el host (p. ej. Anthropic con Claude Code, o el que tengas configurado en Opencode).
- El **bot de Telegram** manda sus respuestas y avisos a través de los servidores de Telegram.
- Toda la información sigue viviendo en **Microsoft 365**, que es quien la sirve vía Graph.

**¿Qué permisos necesita y por qué?**
`npm run auth` pide hoy **16 permisos delegados** (`GRAPH_SCOPES` en `src/auth.ts`):
- Correo: `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `MailboxSettings.ReadWrite`
- Archivos: `Files.ReadWrite.All`, `Sites.ReadWrite.All` (OneDrive y **SharePoint**)
- Calendario y tareas: `Calendars.ReadWrite`, `Tasks.ReadWrite`
- Otros: `User.Read`, `Contacts.ReadWrite`, `Notes.ReadWrite`, `OnlineMeetings.ReadWrite`, `People.Read`, `Presence.Read`, `Chat.ReadWrite` (**chats de Teams**), `offline_access`

**No son los mínimos**: las 13 herramientas del servidor usan un subconjunto (`src/index.ts` pide 8). Antes de desplegar en un cliente, recorta `GRAPH_SCOPES` a lo que de verdad vaya a usar — sobre todo `Sites.ReadWrite.All` y `Chat.ReadWrite`, que dan acceso amplio.

**¿Puedo limitar las carpetas que clasifica?**
Sí. `taxonomy.json` solo define las reglas que tú pongas. Si no pones reglas para una carpeta, el bot no la toca.

**¿Qué pasa si taxonomy.json tiene errores?**
El bot carga el fallback hardcodeado (7 reglas básicas) y sigue funcionando. Log del error en `dist/bot.log`.
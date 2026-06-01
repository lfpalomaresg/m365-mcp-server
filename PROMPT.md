# Prompt Original — M365 Personal MCP Server

## Contexto
Este archivo documenta los prompts de arquitectura utilizados para construir el servidor MCP de Microsoft 365 con Claude Code.

---

## Prompt de Arquitectura Final (versión usada)

```
Actúa como un ingeniero de sistemas experto de nivel Staff, especializado en Node.js,
TypeScript y el Model Context Protocol (MCP). Vamos a desarrollar un servidor MCP local
de producción en mi máquina para conectar mi cuenta PERSONAL de Microsoft 365 a Claude Code
mediante la API de Microsoft Graph, adaptándonos a las restricciones de las cuentas personales.

### PASO 1: Verificación de Credenciales Personales
Dado que estamos utilizando el portal simplificado de administración de identidades para
cuentas personales, necesitamos:
1. Tipo de cuenta: "Cuentas en cualquier directorio organizativo y cuentas Microsoft personales"
2. Plataforma/URI de redirección: Tipo 'Cliente público/móvil' apuntando a 'http://localhost:3000'
3. CLIENT_ID (ID de aplicación)

### PASO 2: Inicialización del Entorno Local
- Node.js con TypeScript (tsconfig ES2022)
- Dependencias: @modelcontextprotocol/sdk, @azure/msal-node,
  @microsoft/microsoft-graph-client, isomorphic-fetch, dotenv, @types/node

### PASO 3: Servidor MCP con PKCE Auth Flow
Autenticación mediante PKCE con servidor HTTP local (más fiable que Device Code Flow
para cuentas personales con apps registradas en tenants corporativos).

Herramientas expuestas:
1. OneDrive: search_onedrive_files, download_onedrive_file, upload_onedrive_file, update_excel_sheet
2. Outlook: get_latest_emails, send_outlook_email, download_email_attachments
3. Productividad: manage_todo_tasks, sync_calendar_events

### PASO 4: Integración en Claude Code
Registro global en ~/.claude.json bajo el nombre "m365-personal-suite"
```

---

## Stack Técnico

| Componente | Tecnología |
|------------|------------|
| Runtime | Node.js v24 |
| Lenguaje | TypeScript 5.x (ES2022) |
| Protocolo | Model Context Protocol (MCP) SDK |
| Auth | MSAL Node v2 — PKCE Flow |
| API | Microsoft Graph v1.0 |
| Registro de app | Azure App Registration (tenant corporativo, soporte personal) |

## Permisos Microsoft Graph configurados (15)

| Permiso | Uso |
|---------|-----|
| User.Read | Perfil básico |
| Mail.Read / Mail.ReadWrite / Mail.Send | Correo Outlook |
| Calendars.ReadWrite | Calendario |
| Files.ReadWrite.All | OneDrive completo |
| Tasks.ReadWrite | Microsoft To-Do |
| Contacts.ReadWrite | Contactos |
| Notes.ReadWrite | OneNote |
| OnlineMeetings.ReadWrite | Reuniones Teams |
| People.Read | Personas frecuentes |
| Presence.Read | Estado Teams |
| Sites.ReadWrite.All | SharePoint |
| Chat.ReadWrite | Chat Teams |
| MailboxSettings.ReadWrite | Configuración buzón |

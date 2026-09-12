# G:\Mi unidad\claude_workspace\m365_mcp_server\telegram_bot.py
# Telegram Bot for Outlook M365 Automation (Windows/Mac/Mobile)
# Runs 100% natively with ZERO external dependencies (stdlib only)

import os
import sys
import json
import time
import base64
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

APP_DIR = os.path.dirname(__file__)

# ─── Config ────────────────────────────────────────────────────────────────────

def load_env():
    env_vars = {}
    env_path = os.path.join(APP_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

env = load_env()

BOT_TOKEN = env.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = env.get("TELEGRAM_ALLOWED_USER_ID")

if not BOT_TOKEN or not ALLOWED_USER_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USER_ID missing in .env")
    sys.exit(1)

ALLOWED_USER_ID = int(ALLOWED_USER_ID)
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Remitentes importantes para notificaciones push (email o nombre)
IMPORTANT_SENDERS = env.get("TELEGRAM_IMPORTANT_SENDERS", "").split(",")
IMPORTANT_SENDERS = [s.strip().lower() for s in IMPORTANT_SENDERS if s.strip()]

NOTIFY_CHECK_SECONDS = int(env.get("TELEGRAM_NOTIFY_INTERVAL", "120"))

# ─── Token & HTTP ──────────────────────────────────────────────────────────────

def get_graph_token():
    try:
        node_script = os.path.join(APP_DIR, "dist", "token.js")
        r = subprocess.run(["node", node_script], capture_output=True,
                           text=True, encoding="utf-8")
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception as e:
        print(f"Token error: {e}")
    return None

def make_request(url, method="GET", headers=None, body=None, timeout=40):
    headers = headers or {}
    req = urllib.request.Request(url, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    if body:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as e:
        print(f"HTTP error: {e}")
        return None

def send_telegram(chat_id, text, reply_markup=None):
    make_request(
        f"{TELEGRAM_API_URL}/sendMessage",
        method="POST",
        body={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            **({"reply_markup": reply_markup} if reply_markup else {})
        }
    )

def edit_telegram(chat_id, message_id, text, reply_markup=None):
    make_request(
        f"{TELEGRAM_API_URL}/editMessageText",
        method="POST",
        body={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown",
            **({"reply_markup": reply_markup} if reply_markup else {})
        }
    )

def answer_callback(callback_id, text=None):
    body = {"callback_query_id": callback_id}
    if text:
        body["text"] = text
    make_request(f"{TELEGRAM_API_URL}/answerCallbackQuery", method="POST", body=body)

# ─── Graph API ─────────────────────────────────────────────────────────────────

def call_graph(endpoint, method="GET", body=None):
    token = get_graph_token()
    if not token:
        return {"_error": "no_token"}
    url = f"https://graph.microsoft.com/v1.0{endpoint}".replace(" ", "%20")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    result = make_request(url, method=method, headers=headers, body=body)
    if result is None:
        return {"_error": "http_failed"}
    return result

def local_midnight_utc():
    """Return ISO timestamp for start of today in local timezone, in UTC."""
    now = datetime.now().astimezone()
    local_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def format_email_list(emails):
    if not emails:
        return "Sin resultados."
    msg = ""
    for i, m in enumerate(emails, 1):
        sender = (m.get("from", {}) or {}).get("emailAddress", {}) or {}
        name = sender.get("name", "?")
        subj = m.get("subject", "Sin asunto")
        t = (m.get("receivedDateTime", "") or "")[11:16]
        msg += f"{i}. [{t}] *{name}*:\n   _{subj}_\n\n"
    return msg

# ─── Folder Resolution ─────────────────────────────────────────────────────────

def resolve_folder_id(path):
    segments = [s.strip() for s in path.split("/") if s.strip()]
    if not segments:
        return None
    inbox_res = call_graph("/me/mailFolders/inbox")
    if not inbox_res or "_error" in inbox_res:
        return None
    inbox_id = inbox_res.get("id")
    inbox_name = inbox_res.get("displayName")
    current_id = inbox_id
    start_idx = 0
    if segments[0].lower() in ["inbox", "bandeja de entrada", (inbox_name or "").lower()]:
        start_idx = 1
    for i in range(start_idx, len(segments)):
        subs = call_graph(f"/me/mailFolders/{current_id}/childFolders?$top=100")
        if not subs or "_error" in subs:
            return None
        found = next(
            (f for f in subs.get("value", [])
             if f.get("displayName", "").lower() == segments[i].lower()),
            None
        )
        if not found:
            return None
        current_id = found.get("id")
    return current_id

# ─── Taxonomy & Classification ─────────────────────────────────────────────────

TAXONOMY = {
    "01_OPERATIVA/01_RRHH": ["baja", "nomina", "trabajadora", "sara rengel",
                             "rosa santos", "excedencia", "lyf", "finiquito", "contrato"],
    "01_OPERATIVA/02_COMERCIAL_EVENTOS": ["stop sales", "cierre de ventas",
        "tarifa fit", "ttoo", "almudena ayuso", "cierre ventas"],
    "01_OPERATIVA/03_FINANZAS": ["arqueo", "caja", "cierre de caja",
        "factura", "abono", "cargo", "no-show", "no show", "no presentado"],
    "00_CONTROL_DIARIO/07_REVISAR_EVENTOS_BODAS_GRUPOS": ["grupo", "rooming",
        "roster", "coctel", "degustacion", "ods", "orden de servicio",
        "sunshine weddings", "rick steves", "lauren crumplin"],
    "00_CONTROL_DIARIO/08_REVISAR_INCIDENCIAS_AVERIAS": ["sancion", "multa",
        "incidencia", "averia", "sixt", "carcagno"],
    "01_OPERATIVA/08_MARKETING": ["newsletter", "substack", "hosteltur",
        "agoda", "groupon", "raiola", "eoi", "awards", "smart travel"],
    "PEDIDOS": ["pedido", "albaran", "frutas eladio", "ly company",
        "qualianza", "calidad pascual", "huevos", "leche", "agua"]
}

def classify_unread(apply_now=False):
    res = call_graph(
        "/me/messages?$filter=isRead eq false&$top=30"
        "&$select=id,subject,sender,receivedDateTime,bodyPreview"
    )
    if not res or "_error" in res:
        err = (res or {}).get("_error", "unknown")
        if err == "no_token":
            return "❌ No hay sesion activa con Microsoft 365. Ejecuta `npm run auth` en el servidor."
        return "❌ Error al conectar con Microsoft Graph."

    emails = res.get("value", [])
    if not emails:
        return "No tienes correos sin leer. Bandeja despejada. 🟢"

    proposed = []
    for email in emails:
        subj = (email.get("subject") or "").lower()
        sender_name = (
            ((email.get("sender") or {}).get("emailAddress") or {}).get("name") or ""
        ).lower()
        body = (email.get("bodyPreview") or "").lower()
        text = f"{subj} {sender_name} {body}"

        folder = next((f for f, kw in TAXONOMY.items() if any(k in text for k in kw)), None)
        if folder:
            proposed.append({
                "id": email["id"],
                "subject": email.get("subject", "?"),
                "target": folder,
                "sender": ((email.get("sender") or {}).get("emailAddress") or {}).get("name", "?")
            })

    if not proposed:
        return (f"Hay {len(emails)} correos sin leer, pero ninguno encaja "
                "en las reglas automaticas. Revisalos manualmente.")

    if apply_now:
        return apply_plan(proposed)

    plan_path = os.path.join(APP_DIR, "dist", "_bot_plan.json")
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(proposed, f, indent=2, ensure_ascii=False)

    msg = f"📋 *Propuesta ({len(proposed)} de {len(emails)} sin leer):*\n\n"
    for i, p in enumerate(proposed, 1):
        msg += f"{i}. *{p['sender']}*:\n   _{p['subject'][:60]}_\n   👉 `{p['target']}`\n\n"
    msg += "Pulsa *Aplicar* para moverlos, o *Cancelar* para ignorar."
    return msg

def apply_plan(proposed=None):
    if proposed is None:
        plan_path = os.path.join(APP_DIR, "dist", "_bot_plan.json")
        if not os.path.exists(plan_path):
            return "No hay plan pendiente. Usa Clasificar primero."
        with open(plan_path, "r", encoding="utf-8") as f:
            proposed = json.load(f)

    ok = 0
    fail = 0
    cache = {}
    for p in proposed:
        fid = cache.get(p["target"])
        if not fid:
            fid = resolve_folder_id(p["target"])
            if fid:
                cache[p["target"]] = fid
        if fid:
            mv = call_graph(f"/me/messages/{p['id']}/move",
                            method="POST", body={"destinationId": fid})
            if mv and "_error" not in mv:
                ok += 1
            else:
                fail += 1
        else:
            fail += 1

    # Cleanup
    plan_path = os.path.join(APP_DIR, "dist", "_bot_plan.json")
    try:
        os.remove(plan_path)
    except OSError:
        pass

    return f"✅ Movidos: {ok}  |  ❌ Fallidos: {fail}"

# ─── Search ────────────────────────────────────────────────────────────────────

def search_emails(query, limit=10):
    q = urllib.parse.quote(query)
    res = call_graph(
        f"/me/messages?$search=%22{q}%22&$top={limit}"
        "&$select=id,subject,from,receivedDateTime,isRead,hasAttachments"
    )
    if not res or "_error" in res:
        return None
    return res.get("value", [])

# ─── Send Email ────────────────────────────────────────────────────────────────

def send_email_via_graph(to, subject, body):
    res = call_graph("/me/sendMail", method="POST", body={
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}]
        }
    })
    return res and "_error" not in res

# ─── Attachments ───────────────────────────────────────────────────────────────

def get_attachment(message_id):
    res = call_graph(f"/me/messages/{message_id}/attachments")
    if not res or "_error" in res:
        return None
    attachments = []
    for att in res.get("value", []):
        if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
            attachments.append({
                "name": att.get("name", "adjunto"),
                "size": att.get("size", 0),
                "contentType": att.get("contentType", "?"),
                "bytes": att.get("contentBytes")
            })
    return attachments

# ─── Inline Keyboard ───────────────────────────────────────────────────────────

def main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📬 Hoy (no leidos)", "callback_data": "hoy"}],
            [{"text": "📋 Clasificar", "callback_data": "clasifica"},
             {"text": "✅ Aplicar", "callback_data": "aplicar"}],
            [{"text": "🔍 Buscar", "callback_data": "buscar"},
             {"text": "✉️ Enviar", "callback_data": "enviar"}],
            [{"text": "📎 Adjuntos", "callback_data": "adjuntos_menu"}],
        ]
    }

def confirm_keyboard(positive_data):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Confirmar", "callback_data": positive_data},
                {"text": "❌ Cancelar", "callback_data": "cancel"}
            ]
        ]
    }

def main_menu_text():
    return "👋 *Asistente M365*\n\nQue quieres hacer?"

# ─── State Machine for /enviar ─────────────────────────────────────────────────

user_state = {}  # {chat_id: {"state": str, "to": str, "subject": str, "body": str}}

# ─── Push Notifications ────────────────────────────────────────────────────────

_last_notify_check = 0
_notified_ids = set()  # avoid notifying same email twice

def check_important_unread():
    global _last_notify_check, _notified_ids
    now = time.time()
    if now - _last_notify_check < NOTIFY_CHECK_SECONDS:
        return []
    _last_notify_check = now

    if not IMPORTANT_SENDERS:
        return []

    # Reuse human-readable name match: get recent unread and filter client-side
    res = call_graph(
        "/me/messages?$filter=isRead eq false&$top=10"
        "&$select=id,subject,from,receivedDateTime"
    )
    if not res or "_error" in res:
        return []

    alerts = []
    for m in res.get("value", []):
        mid = m.get("id")
        if mid in _notified_ids:
            continue
        sender_addr = (((m.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
        sender_name = (((m.get("from") or {}).get("emailAddress") or {}).get("name") or "").lower()
        combined = f"{sender_name} {sender_addr}"
        if any(s in combined for s in IMPORTANT_SENDERS):
            alerts.append(m)
            _notified_ids.add(mid)

    # Keep notified_ids from growing indefinitely
    if len(_notified_ids) > 500:
        _notified_ids = set(list(_notified_ids)[-200:])

    return alerts

# ─── Main Loop ─────────────────────────────────────────────────────────────────

def main():
    print("M365 Telegram Bot starting...")
    if IMPORTANT_SENDERS:
        print(f"Push notifications active for: {IMPORTANT_SENDERS}")
    offset = 0

    while True:
        try:
            # 1. Check for push notifications
            push_alerts = check_important_unread()
            for alert in push_alerts:
                sender_name = (
                    ((alert.get("from") or {}).get("emailAddress") or {}).get("name", "?")
                )
                subj = alert.get("subject", "?")
                send_telegram(
                    ALLOWED_USER_ID,
                    f"🔔 *Correo importante sin leer*\n\n"
                    f"De: *{sender_name}*\n"
                    f"Asunto: _{subj}_\n\n"
                    f"Responde /hoy para ver detalles."
                )

            # 2. Poll Telegram
            url = f"{TELEGRAM_API_URL}/getUpdates?offset={offset}&timeout=30"
            res = make_request(url, timeout=40)
            if not res or not res.get("ok"):
                continue

            for update in res.get("result", []):
                offset = update.get("update_id") + 1

                # ── Callback Query (inline button press) ──
                cb = update.get("callback_query")
                if cb:
                    cb_id = cb.get("id")
                    cb_data = cb.get("data", "")
                    cb_msg = cb.get("message", {})
                    cb_chat_id = cb_msg.get("chat", {}).get("id")
                    cb_user_id = cb.get("from", {}).get("id")
                    if cb_user_id != ALLOWED_USER_ID:
                        answer_callback(cb_id, "No autorizado")
                        continue

                    answer_callback(cb_id)  # dismiss loading spinner

                    if cb_data == "hoy":
                        send_telegram(cb_chat_id, "📬 Buscando correos sin leer de hoy...")
                        midnight = local_midnight_utc()
                        res_emails = call_graph(
                            f"/me/messages?$filter=isRead eq false and "
                            f"receivedDateTime ge {midnight}"
                            f"&$top=15&$select=id,subject,from,receivedDateTime,hasAttachments"
                        )
                        if not res_emails or "_error" in res_emails:
                            send_telegram(cb_chat_id,
                                "❌ Error al conectar con Microsoft Graph.")
                        else:
                            emails = res_emails.get("value", [])
                            if not emails:
                                send_telegram(cb_chat_id,
                                    "No tienes correos sin leer recibidos hoy. 🟢")
                            else:
                                msg = f"📬 *Hoy ({len(emails)} sin leer):*\n\n"
                                msg += format_email_list(emails)
                                send_telegram(cb_chat_id, msg)

                    elif cb_data == "clasifica":
                        send_telegram(cb_chat_id, "📋 Analizando...")
                        resp = classify_unread(apply_now=False)
                        keyboard = confirm_keyboard("confirm_aplicar") if "📋" in resp else None
                        send_telegram(cb_chat_id, resp, reply_markup=keyboard)

                    elif cb_data == "confirm_aplicar":
                        resp = apply_plan()
                        send_telegram(cb_chat_id, resp, reply_markup=main_keyboard())

                    elif cb_data == "aplicar":
                        resp = apply_plan()
                        send_telegram(cb_chat_id, resp, reply_markup=main_keyboard())

                    elif cb_data == "confirm_send":
                        st_send = user_state.get(cb_chat_id, {})
                        if st_send.get("state") == "waiting_confirm":
                            sent = send_email_via_graph(
                                st_send["to"], st_send["subject"], st_send["body"]
                            )
                            user_state.pop(cb_chat_id, None)
                            if sent:
                                send_telegram(cb_chat_id,
                                    f"✅ Correo enviado a *{st_send['to']}*.",
                                    reply_markup=main_keyboard())
                            else:
                                send_telegram(cb_chat_id,
                                    "❌ No se pudo enviar el correo.",
                                    reply_markup=main_keyboard())
                        else:
                            answer_callback(cb_id, "Sesion de envio expirada")

                    elif cb_data == "buscar":
                        user_state[cb_chat_id] = {"state": "waiting_search"}
                        send_telegram(cb_chat_id, "🔍 Escribe lo que quieres buscar en tus correos:")

                    elif cb_data == "enviar":
                        user_state[cb_chat_id] = {"state": "waiting_to"}
                        send_telegram(cb_chat_id, "✉️ *Enviar correo*\n\nDestinatario (email):")

                    elif cb_data == "adjuntos_menu":
                        send_telegram(cb_chat_id,
                            "📎 Para descargar un adjunto, responde con:\n"
                            "`/adjuntos <id_del_mensaje>`\n\n"
                            "Usa Buscar primero para encontrar el mensaje y su ID.")

                    elif cb_data == "cancel":
                        user_state.pop(cb_chat_id, None)
                        send_telegram(cb_chat_id, "Cancelado.", reply_markup=main_keyboard())

                    continue  # callback handled, skip message processing

                # ── Text Message ──
                message = update.get("message")
                if not message:
                    continue

                chat_id = message.get("chat", {}).get("id")
                user_id = message.get("from", {}).get("id")
                if user_id != ALLOWED_USER_ID:
                    continue

                text = (message.get("text") or "").strip()

                # ── State machine for /enviar & /buscar ──
                st = user_state.get(chat_id)

                if st:
                    state_name = st.get("state")

                    if state_name == "waiting_search":
                        user_state.pop(chat_id, None)
                        send_telegram(chat_id, f"🔍 Buscando \"{text}\"...")
                        results = search_emails(text)
                        if results is None:
                            send_telegram(chat_id, "❌ Error al buscar.")
                        elif not results:
                            send_telegram(chat_id,
                                f"No encontre resultados para \"{text}\".")
                        else:
                            msg = f"🔍 *Resultados para \"{text}\" ({len(results)}):*\n\n"
                            msg += format_email_list(results)
                            send_telegram(chat_id, msg, reply_markup=main_keyboard())

                    elif state_name == "waiting_to":
                        st["to"] = text
                        st["state"] = "waiting_subject"
                        send_telegram(chat_id, "Asunto del correo:")

                    elif state_name == "waiting_subject":
                        st["subject"] = text
                        st["state"] = "waiting_body"
                        send_telegram(chat_id, "Cuerpo del mensaje:")

                    elif state_name == "waiting_body":
                        st["body"] = text
                        st["state"] = "waiting_confirm"
                        summary = (
                            f"✉️ *Confirmar envio:*\n\n"
                            f"*Para:* {st['to']}\n"
                            f"*Asunto:* {st['subject']}\n"
                            f"*Cuerpo:* {st['body'][:200]}"
                        )
                        send_telegram(chat_id, summary,
                                      reply_markup=confirm_keyboard("confirm_send"))

                    elif state_name == "waiting_confirm":
                        send_telegram(chat_id,
                            "Usa los botones *Confirmar* o *Cancelar* para decidir.",
                            reply_markup=confirm_keyboard("confirm_send"))
                    continue

                # ── Commands ──
                if text in ("/start", "/help"):
                    send_telegram(chat_id, main_menu_text(), reply_markup=main_keyboard())

                elif text == "/hoy":
                    send_telegram(chat_id, "📬 Buscando correos sin leer de hoy...")
                    midnight = local_midnight_utc()
                    res_emails = call_graph(
                        f"/me/messages?$filter=isRead eq false and "
                        f"receivedDateTime ge {midnight}"
                        f"&$top=15&$select=id,subject,from,receivedDateTime,hasAttachments"
                    )
                    if not res_emails or "_error" in res_emails:
                        send_telegram(chat_id,
                            "❌ Error al conectar con Microsoft Graph.")
                    else:
                        emails = res_emails.get("value", [])
                        if not emails:
                            send_telegram(chat_id,
                                "No tienes correos sin leer recibidos hoy. 🟢")
                        else:
                            msg = f"📬 *Hoy ({len(emails)} sin leer):*\n\n"
                            msg += format_email_list(emails)
                            send_telegram(chat_id, msg)

                elif text == "/clasifica":
                    send_telegram(chat_id, "📋 Analizando...")
                    resp = classify_unread(apply_now=False)
                    keyboard = confirm_keyboard("confirm_aplicar") if resp.startswith("📋") else None
                    send_telegram(chat_id, resp, reply_markup=keyboard)

                elif text == "/aplicar":
                    resp = apply_plan()
                    send_telegram(chat_id, resp, reply_markup=main_keyboard())

                elif text.startswith("/buscar "):
                    query = text[len("/buscar "):].strip()
                    if not query:
                        send_telegram(chat_id, "Uso: `/buscar <texto>`")
                        continue
                    send_telegram(chat_id, f"🔍 Buscando \"{query}\"...")
                    results = search_emails(query)
                    if results is None:
                        send_telegram(chat_id, "❌ Error al buscar.")
                    elif not results:
                        send_telegram(chat_id,
                            f"No encontre resultados para \"{query}\".")
                    else:
                        msg = f"🔍 *Resultados ({len(results)}):*\n\n"
                        msg += format_email_list(results)
                        send_telegram(chat_id, msg)

                elif text.startswith("/adjuntos "):
                    msg_id = text[len("/adjuntos "):].strip()
                    send_telegram(chat_id, "📎 Descargando adjuntos...")
                    atts = get_attachment(msg_id)
                    if atts is None:
                        send_telegram(chat_id, "❌ Error al acceder a los adjuntos.")
                    elif not atts:
                        send_telegram(chat_id,
                            "Ese mensaje no tiene adjuntos descargables.")
                    else:
                        saved = os.path.join(APP_DIR, "dist", "attachments")
                        os.makedirs(saved, exist_ok=True)
                        filenames = []
                        for att in atts:
                            fpath = os.path.join(saved, att["name"])
                            data = base64.b64decode(att["bytes"])
                            with open(fpath, "wb") as f:
                                f.write(data)
                            filenames.append(f"{att['name']} ({len(data)} bytes)")
                        send_telegram(chat_id,
                            "📎 *Adjuntos guardados:*\n\n" +
                            "\n".join(f"  • {n}" for n in filenames))

                elif text == "/enviar":
                    user_state[chat_id] = {"state": "waiting_to"}
                    send_telegram(chat_id, "✉️ *Enviar correo*\n\nDestinatario (email):")

                elif text.startswith("/"):
                    send_telegram(chat_id,
                        "Comando no reconocido. Usa los botones o /help.",
                        reply_markup=main_keyboard())

                else:
                    # Free text: offer keyboard
                    send_telegram(chat_id, main_menu_text(), reply_markup=main_keyboard())

        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(5)

        time.sleep(1)

if __name__ == "__main__":
    main()
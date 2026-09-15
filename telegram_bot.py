# G:\Mi unidad\claude_workspace\m365_mcp_server\telegram_bot.py
# Telegram Bot for Outlook M365 Automation (Windows/Mac/Mobile)
# Runs 100% natively with ZERO external dependencies (stdlib only)

import os
import sys
import re
import json
import time
import random
import html as html_mod
import base64
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

APP_DIR = os.path.dirname(__file__)
DIST_DIR = os.path.join(APP_DIR, "dist")
STATE_FILE = os.path.join(DIST_DIR, "_bot_state.json")
LOG_FILE = os.path.join(DIST_DIR, "bot.log")
PLAN_FILE = os.path.join(DIST_DIR, "_bot_plan.json")
ATTACH_DIR = os.path.join(DIST_DIR, "attachments")

# ─── Logging ───────────────────────────────────────────────────────────────────

def _redact(text):
    """Nunca escribir el token del bot: va dentro de la URL de la API de Telegram
    (2026-09-16: salía en claro en dist/bot.log en cada error de red)."""
    return re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot<token>", str(text))

def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {_redact(msg)}"
    print(line)
    try:
        os.makedirs(DIST_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

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
    log("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USER_ID missing in .env")
    sys.exit(1)

ALLOWED_USER_ID = int(ALLOWED_USER_ID)
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

IMPORTANT_SENDERS = [s.strip().lower() for s in env.get("TELEGRAM_IMPORTANT_SENDERS", "").split(",") if s.strip()]
NOTIFY_CHECK_SECONDS = int(env.get("TELEGRAM_NOTIFY_INTERVAL", "120"))
AUTO_CLASSIFY_SECONDS = int(env.get("TELEGRAM_AUTO_CLASSIFY_INTERVAL", "0"))  # 0 = disabled
AUTO_CLASSIFY_NOTIFY = env.get("TELEGRAM_AUTO_CLASSIFY_NOTIFY", "true").lower() == "true"
# 2026-09-16: alias LiteLLM del explorador residente del stack (nunca un modelo fijo de LM Studio:
# el qwen3.8-27b que había aquí ocupaba 16 GB y bloqueaba el arranque de opencode).
LLM_API_URL = env.get("TELEGRAM_LLM_URL", "http://localhost:4000/v1/chat/completions")
LLM_MODEL = env.get("TELEGRAM_LLM_MODEL", "local-fast")
LLM_ENABLED = env.get("TELEGRAM_LLM_ENABLED", "true").lower() == "true"

SYSTEM_PROMPT = """Eres el asistente de correo M365. Tu tarea es interpretar mensajes en español y decidir qué acción ejecutar. Responde SIEMPRE solo con un JSON válido, sin explicaciones ni markdown.

Acciones disponibles:
- hoy: mostrar correos sin leer recibidos hoy
- clasifica: clasificar y mover correos no leídos según reglas
- buscar: buscar correos por texto. params: query (texto a buscar)
- calendario: ver eventos de hoy
- tareas: ver tareas pendientes
- enviar: enviar un correo. params: to (destinatario), subject (asunto), body (cuerpo)
- ver: leer un correo específico. params: num (número del correo en la última lista)
- responder: responder a un correo. params: num (número), text (respuesta)
- stats: ver estadísticas del bot
- unknown: no se entiende o no es una acción de correo

Responde con el JSON exacto. Ejemplos:
Usuario: "¿tengo correos nuevos?"
Respuesta: {"action": "hoy"}

Usuario: "busca correos de Juan"
Respuesta: {"action": "buscar", "params": {"query": "Juan"}}

Usuario: "manda un correo a María asunto reunión cuerpo nos vemos mañana"
Respuesta: {"action": "enviar", "params": {"to": "María", "subject": "reunión", "body": "nos vemos mañana"}}

Usuario: "¿qué tiempo hace?"
Respuesta: {"action": "unknown"}

Usuario: "clasifica mis correos"
Respuesta: {"action": "clasifica"}

Usuario: "qué tareas tengo"
Respuesta: {"action": "tareas"}

Usuario: "leo el correo 3"
Respuesta: {"action": "ver", "params": {"num": "3"}}

Usuario: "responde al 2 diciendo que mañana a las 10"
Respuesta: {"action": "responder", "params": {"num": "2", "text": "mañana a las 10"}}

Usuario: "cómo va el bot"
Respuesta: {"action": "stats"}"""

# ─── Stats ──────────────────────────────────────────────────────────────────────

stats = {
    "classified_total": 0,
    "moved_total": 0,
    "failed_total": 0,
    "api_calls": 0,
    "last_classify": None,
    "start_time": None,
}

# ─── Persistent state ──────────────────────────────────────────────────────────

user_state = {}     # {chat_id: {"state": ..., "to": ..., "subject": ..., "body": ..., "reply_to": ...}}
last_results = {}   # {chat_id_str: {short_id: message_id}}

def save_state():
    try:
        os.makedirs(DIST_DIR, exist_ok=True)
        # No persistimos cuerpos de email ni destinatario para evitar leaks
        safe_state = {}
        for cid, s in user_state.items():
            ss = {"state": s.get("state")}
            if s.get("state") == "waiting_confirm":
                ss["to"] = s.get("to", "")
                ss["subject"] = s.get("subject", "")
                ss["has_body"] = True  # indicador, no el cuerpo
            elif s.get("reply_to"):
                ss["reply_to"] = s["reply_to"]
            safe_state[str(cid)] = ss
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"user_state": safe_state, "last_results": last_results}, f, ensure_ascii=False)
    except Exception as e:
        log(f"save_state error: {e}")

def load_state():
    global user_state, last_results
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                user_state = data.get("user_state", {})
                # Convert string keys back to int
                user_state = {int(k): v for k, v in user_state.items()}
                last_results = data.get("last_results", {})
    except Exception as e:
        log(f"load_state error: {e}")

# ─── Token & HTTP ──────────────────────────────────────────────────────────────

TOKEN_CACHE_PATH = os.path.join(os.path.expanduser("~"), ".m365-mcp", ".token_cache.json")
GRAPH_SCOPES_STR = "Mail.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite Files.ReadWrite.All Tasks.ReadWrite offline_access"

def _read_token_from_cache():
    """Lee el access token directamente del cache MSAL sin spawnear Node.js.
    Retorna (token, expires_on) o (None, None)."""
    try:
        if not os.path.exists(TOKEN_CACHE_PATH):
            return None, None
        with open(TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        at_section = cache.get("AccessToken", {})
        if not at_section:
            return None, None
        # Buscar el token con el target que necesitamos (Mail.Read etc.)
        for entry in at_section.values():
            if not isinstance(entry, dict):
                continue
            target = entry.get("target", "")
            if "Mail.Read" in target and "offline_access" in target:
                secret = entry.get("secret")
                expires = entry.get("expires_on")
                if secret and expires:
                    return secret, expires
        # Sin token de Mail no se devuelve otro cualquiera (otro scope → 401 en bucle):
        # el fallback de Node.js refresca el correcto.
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        pass
    return None, None

def get_graph_token():
    """Obtiene un token de acceso a Microsoft Graph.
    Primero intenta leerlo del cache MSAL (Python puro, sin subprocess).
    Si el token no existe o ha caducado, spawn ea Node.js para refrescarlo."""
    secret, expires_on = _read_token_from_cache()
    now = int(time.time())
    if secret and expires_on and int(expires_on) > now + 300:
        return secret  # Token válido con >5 min de margen

    # Fallback: Node.js subprocess (MSAL se encarga del refresh)
    try:
        node_script = os.path.join(APP_DIR, "dist", "token.js")
        r = subprocess.run(["node", node_script], capture_output=True,
                           text=True, encoding="utf-8")
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception as e:
        log(f"Token error: {e}")
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
            raw = res.read().decode("utf-8")
            if not raw.strip():
                return {"_status": res.status}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        log(f"HTTP {e.code} on {sanitize_url(url)}: {e.reason}")
        return {"_error": f"http_{e.code}"}
    except Exception as e:
        log(f"HTTP error on {sanitize_url(url)}: {e}")
        return None


def sanitize_url(url):
    """Strip query params (search terms, ids) from a URL before logging."""
    base = _redact(url).split("?")[0]
    # Keep the path but drop anything after '?' which may contain PII/search terms.
    # Also mask message/folder ids (long base64-like tokens) in the path.
    return re.sub(r"/[A-Za-z0-9_\-]{20,}", "/<id>", base)

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

_last_graph_request = 0.0
MIN_GRAPH_INTERVAL = 0.2          # segundos entre peticiones Graph (throttle básico)
MAX_RETRIES = 3

def _throttle_graph():
    """Evita sobrepasar el rate limit de Microsoft Graph espaciando peticiones."""
    global _last_graph_request
    now = time.time()
    wait = MIN_GRAPH_INTERVAL - (now - _last_graph_request)
    if wait > 0:
        time.sleep(wait)
    _last_graph_request = time.time()

def call_graph(endpoint, method="GET", body=None):
    """Llamada a Graph con throttle y backoff exponencial ante 429."""
    stats["api_calls"] += 1
    for attempt in range(MAX_RETRIES + 1):
        _throttle_graph()
        token = get_graph_token()
        if not token:
            return {"_error": "no_token"}
        url = f"https://graph.microsoft.com/v1.0{endpoint}".replace(" ", "%20")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        result = make_request(url, method=method, headers=headers, body=body)
        if result is None:
            return {"_error": "http_failed"}
        if result.get("_error") == "http_429" and attempt < MAX_RETRIES:
            wait = (2 ** attempt) + random.uniform(0, 0.5)
            log(f"Graph rate limited (429), reintento {attempt + 1} en {wait:.1f}s")
            time.sleep(wait)
            continue
        return result
    return {"_error": "http_429"}

def graph_error_text(res):
    if not res or "_error" not in res:
        return None
    err = res["_error"]
    if err == "no_token":
        return ("❌ No hay sesion activa con Microsoft 365.\n"
                "Ejecuta `npm run auth` en el servidor y reinicia el bot.")
    if err == "http_401":
        return ("❌ El token de Microsoft 365 ha caducado.\n"
                "Ejecuta `npm run auth` en el servidor y reinicia el bot.")
    if err == "http_429":
        return "❌ Microsoft Graph ha limitado las peticiones. Espera un momento y reintenta."
    return "❌ Error al conectar con Microsoft Graph."

def local_midnight_utc():
    now = datetime.now().astimezone()
    local_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc)

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html_mod.unescape(text).strip()

def format_email_list(emails, show_ids=True):
    if not emails:
        return "Sin resultados."
    msg = ""
    for i, m in enumerate(emails, 1):
        sender = (m.get("from", {}) or {}).get("emailAddress", {}) or {}
        name = sender.get("name", "?")
        subj = (m.get("subject") or "Sin asunto")[:70]
        t = (m.get("receivedDateTime", "") or "")[11:16]
        prefix = f"{i}." if show_ids else "•"
        att = "📎" if m.get("hasAttachments") else ""
        msg += f"{prefix} [{t}] {att}*{name}*:\n   _{subj}_\n"
    msg += "\nResponde `/ver <nº>` para leerlo, o usa los botones de accion."
    return msg

def register_results(chat_id, emails):
    """Map short ids (1-based) to Graph message ids, persisted."""
    mapping = {}
    for i, m in enumerate(emails, 1):
        mid = m.get("id")
        if mid:
            mapping[str(i)] = mid
    last_results[str(chat_id)] = mapping
    save_state()
    return mapping

def register_alert(chat_id, msg_id):
    """Registra un aviso push con id corto propio ("a1", "a2"…) SIN machacar la última
    lista de /hoy o /buscar (antes la sustituía por {"1": aviso} y "responde al 1"
    podía ir al correo equivocado)."""
    mapping = last_results.setdefault(str(chat_id), {})
    n = 1
    while f"a{n}" in mapping:
        n += 1
    short = f"a{n}"
    mapping[short] = msg_id
    save_state()
    return short

# ─── Folder Resolution ─────────────────────────────────────────────────────────

_folder_cache = {}   # {path: folder_id}, persistido en state
CACHE_FILE = os.path.join(DIST_DIR, "_folder_cache.json")

def load_folder_cache():
    global _folder_cache
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _folder_cache = json.load(f)
            log(f"Folder cache loaded: {len(_folder_cache)} entries")
    except Exception:
        _folder_cache = {}

def save_folder_cache():
    try:
        os.makedirs(DIST_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_folder_cache, f, ensure_ascii=False)
    except Exception:
        pass

def resolve_folder_id(path):
    if path in _folder_cache:
        return _folder_cache[path]

    segments = [s.strip() for s in path.split("/") if s.strip()]
    if not segments:
        return None
    inbox_res = call_graph("/me/mailFolders/inbox")
    if not inbox_res or "_error" in inbox_res:
        return None
    inbox_id = inbox_res.get("id")
    inbox_name = (inbox_res.get("displayName") or "").lower()
    current_id = inbox_id
    start_idx = 0
    if segments[0].lower() in ["inbox", "bandeja de entrada", inbox_name]:
        start_idx = 1
    for i in range(start_idx, len(segments)):
        subs = call_graph(f"/me/mailFolders/{current_id}/childFolders?$top=100")
        if not subs or "_error" in subs:
            return None
        found = next(
            (f for f in subs.get("value", [])
             if (f.get("displayName") or "").lower() == segments[i].lower()),
            None
        )
        if not found:
            return None
        current_id = found.get("id")
    _folder_cache[path] = current_id
    save_folder_cache()
    return current_id

def get_archive_folder_id():
    res = call_graph("/me/mailFolders/archive")
    if res and "_error" not in res and res.get("id"):
        return res["id"]
    # Fallback: look for a folder named "Archive" / "Archivo" under inbox
    return resolve_folder_id("Archivo") or resolve_folder_id("Archive")

# ─── Email Actions ─────────────────────────────────────────────────────────────

def get_message_body(msg_id):
    res = call_graph(
        f"/me/messages/{msg_id}?$select=id,subject,from,receivedDateTime,bodyPreview,body,hasAttachments"
    )
    if not res or "_error" in res:
        return None
    body_html = ((res.get("body") or {}).get("content")) or ""
    preview = res.get("bodyPreview") or ""
    plain = strip_html(body_html) if body_html else preview
    return {
        "id": msg_id,
        "subject": res.get("subject", "?"),
        "from": ((res.get("from") or {}).get("emailAddress") or {}).get("name", "?"),
        "received": res.get("receivedDateTime", ""),
        "preview": preview,
        "body": plain,
        "hasAttachments": res.get("hasAttachments", False)
    }

def mark_read(msg_id):
    res = call_graph(f"/me/messages/{msg_id}", method="PATCH", body={"isRead": True})
    return res and "_error" not in res

def archive_message(msg_id):
    folder_id = get_archive_folder_id()
    if not folder_id:
        return False
    res = call_graph(f"/me/messages/{msg_id}/move", method="POST",
                     body={"destinationId": folder_id})
    return res and "_error" not in res

def delete_message(msg_id):
    res = call_graph(f"/me/messages/{msg_id}", method="DELETE")
    return res is not None and "_error" not in res

def reply_message(msg_id, comment):
    res = call_graph(f"/me/messages/{msg_id}/reply", method="POST",
                     body={"comment": comment})
    return res is not None and "_error" not in res

# ─── Taxonomy & Classification ─────────────────────────────────────────────────

TAXONOMY_FILE = os.path.join(APP_DIR, "taxonomy.json")
_taxonomy_mtime = 0
TAXONOMY = []  # [{folder, keywords, if_sender?, if_subject_contains?}]
_keyword_index = {}  # {keyword_lower: folder} para rules sin condiciones

def _build_keyword_index(rules):
    """Índice plano keyword→folder para rules sin condiciones adicionales."""
    idx = {}
    for rule in rules:
        if rule.get("if_sender") or rule.get("if_subject_contains"):
            continue  # estas rules se chequean individualmente
        for kw in rule.get("keywords", []):
            idx[kw] = rule["folder"]
    return idx

def load_taxonomy():
    global TAXONOMY, _taxonomy_mtime, _keyword_index
    if os.path.exists(TAXONOMY_FILE):
        try:
            mtime = os.path.getmtime(TAXONOMY_FILE)
            if mtime == _taxonomy_mtime and TAXONOMY:
                return
            with open(TAXONOMY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_rules = data.get("rules", [])
            rules = []
            for r in raw_rules:
                folder = r.get("folder", "")
                if not folder:
                    continue
                rule = {"folder": folder, "keywords": [k.lower() for k in r.get("keywords", [])]}
                if r.get("if_sender"):
                    rule["if_sender"] = r["if_sender"].lower()
                if r.get("if_subject_contains"):
                    rule["if_subject_contains"] = r["if_subject_contains"].lower()
                rules.append(rule)
            if rules:
                TAXONOMY = rules
                _keyword_index = _build_keyword_index(rules)
                _taxonomy_mtime = mtime
                cond_rules = sum(1 for r in rules if r.get("if_sender") or r.get("if_subject_contains"))
                log(f"Taxonomy loaded from taxonomy.json: {len(TAXONOMY)} rules ({cond_rules} condicionales), {len(_keyword_index)} flat keywords")
                return
            else:
                log("taxonomy.json found but contains no valid rules, using defaults")
        except (json.JSONDecodeError, OSError) as e:
            log(f"Error loading taxonomy.json: {e}, using defaults")
    # Fallback: hardcoded
    TAXONOMY = [
        {"folder": "01_OPERATIVA/01_RRHH", "keywords": ["baja", "nomina", "trabajadora", "sara rengel", "rosa santos", "excedencia", "lyf", "finiquito", "contrato"]},
        {"folder": "01_OPERATIVA/02_COMERCIAL_EVENTOS", "keywords": ["stop sales", "cierre de ventas", "tarifa fit", "ttoo", "almudena ayuso", "cierre ventas"]},
        {"folder": "01_OPERATIVA/03_FINANZAS", "keywords": ["arqueo", "caja", "cierre de caja", "factura", "abono", "cargo", "no-show", "no show", "no presentado"]},
        {"folder": "00_CONTROL_DIARIO/07_REVISAR_EVENTOS_BODAS_GRUPOS", "keywords": ["grupo", "rooming", "roster", "coctel", "degustacion", "ods", "orden de servicio", "sunshine weddings", "rick steves", "lauren crumplin"]},
        {"folder": "00_CONTROL_DIARIO/08_REVISAR_INCIDENCIAS_AVERIAS", "keywords": ["sancion", "multa", "incidencia", "averia", "sixt", "carcagno"]},
        {"folder": "01_OPERATIVA/08_MARKETING", "keywords": ["newsletter", "substack", "hosteltur", "agoda", "groupon", "raiola", "eoi", "awards", "smart travel"]},
        {"folder": "PEDIDOS", "keywords": ["pedido", "albaran", "frutas eladio", "ly company", "qualianza", "calidad pascual", "huevos", "leche", "agua"]},
    ]
    _keyword_index = _build_keyword_index(TAXONOMY)
    _taxonomy_mtime = 0
    log(f"Taxonomy loaded from built-in defaults: {len(TAXONOMY)} rules")

def fetch_unread(top=30):
    res = call_graph(
        f"/me/messages?$filter=isRead eq false&$top={top}"
        "&$select=id,subject,from,receivedDateTime,bodyPreview"
    )
    if not res or "_error" in res:
        return None
    emails = res.get("value", [])
    log(f"fetch_unread: filter=isRead eq false, returned {len(emails)} emails")
    return emails

def classify_unread(chat_id=None, apply_now=False):
    load_taxonomy()  # recarga si taxonomy.json cambió
    emails = fetch_unread()
    if emails is None:
        return "❌ Error al conectar con Microsoft Graph."

    if not emails:
        return "No tienes correos sin leer. Bandeja despejada. 🟢"

    proposed = []
    kw_index = _keyword_index
    cond_rules = [r for r in TAXONOMY if r.get("if_sender") or r.get("if_subject_contains")]

    for email in emails:
        subj = (email.get("subject") or "").lower()
        from_field = email.get("from") or {}
        sender_data = from_field.get("emailAddress") or {}
        sender_name = (sender_data.get("name") or "").lower()
        sender_addr = (sender_data.get("address") or "").lower()
        body = (email.get("bodyPreview") or "").lower()
        text = f"{subj} {sender_name} {body}"

        folder = None

        # 1. Fast path: keyword index (rules sin condiciones)
        for kw, fld in kw_index.items():
            if kw in text:
                folder = fld
                break

        # 2. Condicionales: si no matcheó por keyword, evaluar rules con condiciones
        if not folder:
            for rule in cond_rules:
                match = True
                if rule.get("if_sender") and rule["if_sender"] not in f"{sender_name} {sender_addr}":
                    match = False
                if match and rule.get("if_subject_contains") and rule["if_subject_contains"] not in subj:
                    match = False
                if match and rule.get("keywords"):
                    if not any(kw in text for kw in rule["keywords"]):
                        match = False
                if match:
                    folder = rule["folder"]
                    break

        if folder:
            proposed.append({
                "id": email["id"],
                "subject": email.get("subject", "?"),
                "target": folder,
                "sender": sender_name
            })

    if not proposed:
        register_results(chat_id, emails) if chat_id else None
        return (f"Hay {len(emails)} correos sin leer, pero ninguno encaja "
                "en las reglas automaticas. Revisalos manualmente con /hoy.")

    if apply_now:
        return apply_plan(proposed)

    os.makedirs(DIST_DIR, exist_ok=True)
    with open(PLAN_FILE, "w", encoding="utf-8") as f:
        json.dump(proposed, f, indent=2, ensure_ascii=False)

    msg = f"📋 *Propuesta ({len(proposed)} de {len(emails)} sin leer):*\n\n"
    for i, p in enumerate(proposed, 1):
        msg += f"{i}. *{p['sender']}*:\n   _{p['subject'][:60]}_\n   👉 `{p['target']}`\n\n"
    msg += "Pulsa *Aplicar* para moverlos, o *Cancelar* para ignorar."
    return msg

def apply_plan(proposed=None):
    if proposed is None:
        if not os.path.exists(PLAN_FILE):
            return "No hay plan pendiente. Usa Clasificar primero."
        with open(PLAN_FILE, "r", encoding="utf-8") as f:
            proposed = json.load(f)

    ok = 0
    fail = 0
    retried = 0
    cache = {}
    for p in proposed:
        fid = cache.get(p["target"])
        if not fid:
            fid = resolve_folder_id(p["target"])
            if fid:
                cache[p["target"]] = fid
        if not fid:
            fail += 1
            continue

        mv = call_graph(f"/me/messages/{p['id']}/move",
                        method="POST", body={"destinationId": fid})
        if mv and "_error" not in mv:
            ok += 1
        elif mv and mv.get("_error") == "http_401":
            # Token caducado a mitad del lote: refrescar y reintentar una vez
            log("apply_plan: token expired, refreshing and retrying...")
            # Forzar refresh via Node.js (salta el cache de Python)
            try:
                node_script = os.path.join(APP_DIR, "dist", "token.js")
                r = subprocess.run(["node", node_script], capture_output=True,
                                   text=True, encoding="utf-8")
                if r.returncode == 0 and r.stdout.strip():
                    mv2 = call_graph(f"/me/messages/{p['id']}/move",
                                     method="POST", body={"destinationId": fid})
                    if mv2 and "_error" not in mv2:
                        ok += 1
                        retried += 1
                        continue
            except Exception:
                pass
            fail += 1
        else:
            fail += 1

    stats["moved_total"] += ok
    stats["failed_total"] += fail

    try:
        os.remove(PLAN_FILE)
    except OSError:
        pass

    result = f"✅ Movidos: {ok}  |  ❌ Fallidos: {fail}"
    if retried:
        result += f"  |  🔄 Reintentados: {retried}"
    return result

# ─── Search / Calendar / Tasks ─────────────────────────────────────────────────

def search_emails(query, limit=10):
    q = urllib.parse.quote(query)
    res = call_graph(
        f"/me/messages?$search=%22{q}%22&$top={limit}"
        "&$select=id,subject,from,receivedDateTime,isRead,hasAttachments"
    )
    if not res or "_error" in res:
        return None
    return res.get("value", [])

def get_today_events():
    start = local_midnight_utc()
    end = start + timedelta(hours=24)
    s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    e = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    res = call_graph(
        f"/me/calendarView?startDateTime={s}&endDateTime={e}"
        "&$top=20&$select=subject,start,end,location"
    )
    if not res or "_error" in res:
        return None
    return res.get("value", [])

def get_todo_tasks():
    res = call_graph("/me/todo/lists")
    if not res or "_error" in res:
        return None
    lists = res.get("value", [])
    if not lists:
        return []
    tasks = []
    for lst in lists[:3]:
        tres = call_graph(f"/me/todo/lists/{lst['id']}/tasks")
        if tres and "_error" not in tres:
            for t in tres.get("value", []):
                if t.get("status") != "completed":
                    due = t.get("dueDateTime") or {}
                    tasks.append({
                        "title": t.get("title", "?"),
                        "list": lst.get("displayName", "?"),
                        "due": due.get("dateTime", "") if isinstance(due, dict) else "",
                        "importance": t.get("importance", "normal")
                    })
    return tasks

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

def get_attachment(msg_id):
    res = call_graph(f"/me/messages/{msg_id}/attachments")
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

# ─── Inline Keyboards ──────────────────────────────────────────────────────────

def main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📬 Hoy", "callback_data": "hoy"},
             {"text": "📋 Clasificar", "callback_data": "clasifica"}],
            [{"text": "🔍 Buscar", "callback_data": "buscar"},
             {"text": "✉️ Enviar", "callback_data": "enviar"}],
            [{"text": "📅 Calendario", "callback_data": "calendario"},
             {"text": "✅ Tareas", "callback_data": "tareas"}],
        ]
    }

def confirm_keyboard(positive_data):
    return {
        "inline_keyboard": [
            [{"text": "✅ Confirmar", "callback_data": positive_data},
             {"text": "❌ Cancelar", "callback_data": "cancel"}]
        ]
    }

def email_actions_keyboard(short_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Leído", "callback_data": f"leido:{short_id}"},
                {"text": "📥 Archivar", "callback_data": f"archivar:{short_id}"},
                {"text": "🗑 Eliminar", "callback_data": f"eliminar:{short_id}"}
            ],
            [{"text": "↩️ Responder", "callback_data": f"responder:{short_id}"}],
            [{"text": "⬅️ Menú", "callback_data": "menu"}]
        ]
    }

def main_menu_text():
    return "👋 *Asistente M365*\n\nQue quieres hacer?"

# ─── Push Notifications ────────────────────────────────────────────────────────

_last_notify_check = 0
_notified_ids = set()

def check_important_unread():
    global _last_notify_check, _notified_ids
    now = time.time()
    if now - _last_notify_check < NOTIFY_CHECK_SECONDS:
        return []
    _last_notify_check = now
    if not IMPORTANT_SENDERS:
        return []

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
        sender = ((m.get("from") or {}).get("emailAddress") or {})
        combined = f"{sender.get('name', '')} {sender.get('address', '')}".lower()
        if any(s in combined for s in IMPORTANT_SENDERS):
            alerts.append(m)
            _notified_ids.add(mid)

    if alerts:
        log(f"check_important_unread: {len(alerts)} important unread found (total unread: {len(res.get('value', []))})")

    if len(_notified_ids) > 500:
        _notified_ids = set(list(_notified_ids)[-200:])
    return alerts

# ─── Message / Callback handlers ───────────────────────────────────────────────

def handle_hoy(chat_id):
    midnight = local_midnight_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    res = call_graph(
        f"/me/messages?$filter=isRead eq false and receivedDateTime ge {midnight}"
        "&$top=15&$select=id,subject,from,receivedDateTime,hasAttachments"
    )
    err = graph_error_text(res)
    if err:
        return err
    emails = res.get("value", [])
    log(f"handle_hoy: filter=isRead eq false and receivedDateTime ge {midnight}, returned {len(emails)} emails")
    if not emails:
        return "No tienes correos sin leer recibidos hoy. 🟢\n\nPrueba /clasifica para ver todos los no leidos sin filtrar por fecha."
    register_results(chat_id, emails)
    return "📬 *Hoy (sin leer):*\n\n" + format_email_list(emails)

def handle_buscar(chat_id, query):
    results = search_emails(query)
    if results is None:
        return "❌ Error al buscar."
    if not results:
        return f"No encontre resultados para \"{query}\"."
    register_results(chat_id, results)
    return f"🔍 *Resultados ({len(results)}):*\n\n" + format_email_list(results)

def handle_ver(chat_id, short_id):
    mapping = last_results.get(str(chat_id), {})
    msg_id = mapping.get(str(short_id))
    if not msg_id:
        return f"No tengo el mensaje nº {short_id}. Lanza /hoy o /buscar primero."
    body = get_message_body(msg_id)
    if not body:
        return "❌ No pude leer ese correo."
    text = (
        f"📧 *{body['subject']}*\n"
        f"De: {body['from']}\n"
        f"Recibido: {body['received'][:16].replace('T', ' ')}\n\n"
        f"{body['body'][:1500]}"
    )
    return text

def handle_calendar(chat_id):
    events = get_today_events()
    if events is None:
        return "❌ Error al leer el calendario."
    if not events:
        return "📅 No tienes eventos hoy."
    msg = f"📅 *Eventos de hoy ({len(events)}):*\n\n"
    for e in events:
        start = (e.get("start") or {}).get("dateTime", "") or ""
        subj = e.get("subject", "Sin título")
        loc = (e.get("location") or {}).get("displayName", "")
        t = start[11:16] if start else "?"
        loc_txt = f" — {loc}" if loc else ""
        msg += f"• [{t}] {subj}{loc_txt}\n"
    return msg

def handle_tareas(chat_id):
    tasks = get_todo_tasks()
    if tasks is None:
        return "❌ Error al leer las tareas."
    if not tasks:
        return "✅ No tienes tareas pendientes."
    msg = f"✅ *Tareas pendientes ({len(tasks)}):*\n\n"
    for t in tasks:
        due = f" — {t['due'][:10]}" if t.get("due") else ""
        star = "⭐" if t.get("importance") == "high" else ""
        msg += f"{star}• {t['title']} ({t['list']}){due}\n"
    return msg

# ─── Natural Language (LLM local) ──────────────────────────────────────────────

def interpret_nl(text):
    """Interpreta lenguaje natural con el LLM local. Retorna dict con action y params, o None si falla."""
    if not LLM_ENABLED or not text.strip():
        return None
    try:
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            "temperature": 0.1,
            "max_tokens": 150,
            "stream": False
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(LLM_API_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=20) as res:
            raw = res.read().decode("utf-8")
            result = json.loads(raw)
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        content = content.strip()
        if "{" in content and "}" in content:
            start = content.index("{")
            end = content.rindex("}") + 1
            content = content[start:end]
        parsed = json.loads(content)
        action = parsed.get("action", "unknown")
        params = parsed.get("params", {})
        return {"action": action, "params": params}
    except Exception as e:
        log(f"LLM interpret error: {e}")
        return None


# ─── Main Loop ─────────────────────────────────────────────────────────────────

def main():
    log("M365 Telegram Bot starting...")
    load_state()
    load_taxonomy()
    load_folder_cache()
    if IMPORTANT_SENDERS:
        log(f"Push notifications active for: {IMPORTANT_SENDERS}")
    offset = 0
    _last_heartbeat = 0.0
    _last_auto_classify = 0.0
    stats["start_time"] = datetime.now().isoformat()
    if AUTO_CLASSIFY_SECONDS > 0:
        log(f"Auto-classify enabled: every {AUTO_CLASSIFY_SECONDS}s")
    if LLM_ENABLED:
        log(f"Natural language enabled: {LLM_MODEL}")
        # Warm-up: primera llamada al LLM para que el modelo cargue en caliente
        try:
            interpret_nl("hola")
        except Exception:
            pass

    while True:
        try:
            # Heartbeat: log alive every 10 min
            now = time.time()
            if now - _last_heartbeat > 600:
                log("heartbeat OK")
                _last_heartbeat = now

            # Push notifications
            for alert in check_important_unread():
                sender_name = (
                    ((alert.get("from") or {}).get("emailAddress") or {}).get("name", "?")
                )
                alert_subj = alert.get("subject", "?")
                short = register_alert(ALLOWED_USER_ID, alert.get("id", ""))
                send_telegram(
                    ALLOWED_USER_ID,
                    f"🔔 *Correo importante sin leer*\n\n"
                    f"De: *{sender_name}*\n"
                    f"Asunto: _{alert_subj}_",
                    reply_markup=email_actions_keyboard(short)
                )

            # Auto-classify
            if AUTO_CLASSIFY_SECONDS > 0 and now - _last_auto_classify > AUTO_CLASSIFY_SECONDS:
                _last_auto_classify = now
                stats["last_classify"] = datetime.now().isoformat()
                result = classify_unread(apply_now=True)
                stats["classified_total"] += 1
                if result and "Movidos" in result:
                    if AUTO_CLASSIFY_NOTIFY and ("Movidos: 0" not in result):
                        send_telegram(ALLOWED_USER_ID, f"🤖 *Auto-clasificacion:* {result}")
                    log(f"Auto-classify: {result}")

            # Poll Telegram
            url = f"{TELEGRAM_API_URL}/getUpdates?offset={offset}&timeout=30"
            res = make_request(url, timeout=40)
            if not res or not res.get("ok"):
                continue

            for update in res.get("result", []):
                offset = update.get("update_id") + 1

                # ── Callback Query ──
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

                    answer_callback(cb_id)
                    handle_callback(cb_chat_id, cb_data, cb_id)
                    continue

                # ── Text Message ──
                message = update.get("message")
                if not message:
                    continue
                chat_id = message.get("chat", {}).get("id")
                user_id = message.get("from", {}).get("id")
                if user_id != ALLOWED_USER_ID:
                    continue
                text = (message.get("text") or "").strip()
                handle_message(chat_id, text)

        except Exception as e:
            log(f"Loop error: {e}")
            time.sleep(5)

        time.sleep(1)

def handle_callback(chat_id, data, cb_id):
    """Dispatch inline button presses."""
    try:
        if data == "menu":
            send_telegram(chat_id, main_menu_text(), reply_markup=main_keyboard())
            return

        if data == "hoy":
            send_telegram(chat_id, "📬 Buscando...")
            send_telegram(chat_id, handle_hoy(chat_id))
            return

        if data == "clasifica":
            send_telegram(chat_id, "📋 Analizando...")
            resp = classify_unread(chat_id=chat_id)
            keyboard = confirm_keyboard("confirm_aplicar") if resp.startswith("📋") else main_keyboard()
            send_telegram(chat_id, resp, reply_markup=keyboard)
            return

        if data == "confirm_aplicar":
            send_telegram(chat_id, apply_plan(), reply_markup=main_keyboard())
            return

        if data == "buscar":
            user_state[chat_id] = {"state": "waiting_search"}
            save_state()
            send_telegram(chat_id, "🔍 Escribe lo que quieres buscar:")
            return

        if data == "enviar":
            user_state[chat_id] = {"state": "waiting_to"}
            save_state()
            send_telegram(chat_id, "✉️ *Enviar correo*\n\nDestinatario (email):")
            return

        if data == "calendario":
            send_telegram(chat_id, handle_calendar(chat_id))
            return

        if data == "tareas":
            send_telegram(chat_id, handle_tareas(chat_id))
            return

        if data == "cancel":
            user_state.pop(chat_id, None)
            save_state()
            send_telegram(chat_id, "Cancelado.", reply_markup=main_keyboard())
            return

        if data == "confirm_send":
            st = user_state.get(chat_id, {})
            if st.get("state") != "waiting_confirm" or not st.get("to") or "body" not in st:
                user_state.pop(chat_id, None)
                save_state()
                send_telegram(chat_id,
                    "La sesion anterior expiro. Inicia un nuevo /enviar.",
                    reply_markup=main_keyboard())
                return
            ok = send_email_via_graph(st["to"], st["subject"], st["body"])
            user_state.pop(chat_id, None)
            save_state()
            send_telegram(chat_id,
                f"✅ Correo enviado a *{st['to']}*." if ok else "❌ No se pudo enviar.",
                reply_markup=main_keyboard())
            return

        if data == "confirm_reply":
            st = user_state.get(chat_id, {})
            user_state.pop(chat_id, None)
            save_state()
            if st.get("state") != "waiting_confirm_reply" or not st.get("reply_to") or not st.get("text"):
                send_telegram(chat_id, "La sesion de respuesta expiro. Lanza /hoy o /buscar.",
                              reply_markup=main_keyboard())
                return
            ok = reply_message(st["reply_to"], st["text"])
            send_telegram(chat_id, "↩️ Respuesta enviada." if ok else "❌ Error al responder.",
                          reply_markup=main_keyboard())
            return

        # Email actions: leido:N / archivar:N / eliminar:N / responder:N
        if ":" in data:
            action, short_id = data.split(":", 1)
            mapping = last_results.get(str(chat_id), {})
            msg_id = mapping.get(short_id)
            if not msg_id:
                answer_callback(cb_id, "Mensaje no disponible. Lanza /hoy o /buscar.")
                return
            if action == "leido":
                ok = mark_read(msg_id)
                send_telegram(chat_id, "✅ Marcado como leído." if ok else "❌ Error.", reply_markup=main_keyboard())
            elif action == "archivar":
                ok = archive_message(msg_id)
                send_telegram(chat_id, "📥 Archivado." if ok else "❌ Error.", reply_markup=main_keyboard())
            elif action == "eliminar":
                ok = delete_message(msg_id)
                send_telegram(chat_id, "🗑 Eliminado." if ok else "❌ Error.", reply_markup=main_keyboard())
            elif action == "responder":
                user_state[chat_id] = {"state": "waiting_reply_body", "reply_to": msg_id}
                save_state()
                send_telegram(chat_id, "↩️ Escribe el texto de tu respuesta:")
            return

        send_telegram(chat_id, main_menu_text(), reply_markup=main_keyboard())

    except Exception as e:
        log(f"Callback error: {e}")

def handle_message(chat_id, text):
    try:
        # State machine
        st = user_state.get(chat_id)
        if st:
            state_name = st.get("state")

            if state_name == "waiting_search":
                user_state.pop(chat_id, None)
                save_state()
                send_telegram(chat_id, f"🔍 Buscando \"{text}\"...")
                send_telegram(chat_id, handle_buscar(chat_id, text), reply_markup=main_keyboard())
                return

            if state_name == "waiting_to":
                st["to"] = text
                st["state"] = "waiting_subject"
                save_state()
                send_telegram(chat_id, "Asunto del correo:")
                return

            if state_name == "waiting_subject":
                st["subject"] = text
                st["state"] = "waiting_body"
                save_state()
                send_telegram(chat_id, "Cuerpo del mensaje:")
                return

            if state_name == "waiting_body":
                st["body"] = text
                st["state"] = "waiting_confirm"
                save_state()
                summary = (
                    f"✉️ *Confirmar envio:*\n\n"
                    f"*Para:* {st['to']}\n"
                    f"*Asunto:* {st['subject']}\n"
                    f"*Cuerpo:* {st['body'][:200]}"
                )
                send_telegram(chat_id, summary, reply_markup=confirm_keyboard("confirm_send"))
                return

            if state_name == "waiting_confirm":
                if "body" not in st:
                    user_state.pop(chat_id, None)
                    save_state()
                    send_telegram(chat_id,
                        "La sesion anterior expiro. Inicia un nuevo /enviar.",
                        reply_markup=main_keyboard())
                    return
                send_telegram(chat_id,
                    "Usa los botones *Confirmar* o *Cancelar*.",
                    reply_markup=confirm_keyboard("confirm_send"))
                return

            if state_name == "waiting_confirm_reply":
                send_telegram(chat_id, "Usa los botones *Confirmar* o *Cancelar*.",
                              reply_markup=confirm_keyboard("confirm_reply"))
                return

            if state_name == "waiting_reply_body":
                reply_to = st.get("reply_to")
                user_state.pop(chat_id, None)
                save_state()
                if reply_to:
                    ok = reply_message(reply_to, text)
                    send_telegram(chat_id,
                        "↩️ Respuesta enviada." if ok else "❌ Error al responder.",
                        reply_markup=main_keyboard())
                else:
                    send_telegram(chat_id, "Sesion de respuesta expirada.", reply_markup=main_keyboard())
                return

        # Commands
        cmd = text.split(" ")[0].lower()

        if text in ("/start", "/help", "/menu"):
            send_telegram(chat_id, main_menu_text(), reply_markup=main_keyboard())

        elif cmd == "/hoy":
            send_telegram(chat_id, "📬 Buscando...")
            send_telegram(chat_id, handle_hoy(chat_id))

        elif cmd == "/clasifica":
            send_telegram(chat_id, "📋 Analizando...")
            resp = classify_unread(chat_id=chat_id)
            keyboard = confirm_keyboard("confirm_aplicar") if resp.startswith("📋") else main_keyboard()
            send_telegram(chat_id, resp, reply_markup=keyboard)

        elif cmd == "/aplicar":
            send_telegram(chat_id, apply_plan(), reply_markup=main_keyboard())

        elif cmd == "/ver":
            parts = text.split(" ", 1)
            short_id = parts[1].strip() if len(parts) > 1 else ""
            if not short_id:
                send_telegram(chat_id, "Uso: `/ver <nº>` (el número sale en /hoy o /buscar).")
                return
            body = handle_ver(chat_id, short_id)
            send_telegram(chat_id, body, reply_markup=email_actions_keyboard(short_id))

        elif cmd == "/buscar":
            query = text[len("/buscar"):].strip()
            if not query:
                user_state[chat_id] = {"state": "waiting_search"}
                save_state()
                send_telegram(chat_id, "🔍 Escribe lo que quieres buscar:")
                return
            send_telegram(chat_id, f"🔍 Buscando \"{query}\"...")
            send_telegram(chat_id, handle_buscar(chat_id, query), reply_markup=main_keyboard())

        elif cmd == "/enviar":
            user_state[chat_id] = {"state": "waiting_to"}
            save_state()
            send_telegram(chat_id, "✉️ *Enviar correo*\n\nDestinatario (email):")

        elif cmd == "/calendario":
            send_telegram(chat_id, handle_calendar(chat_id))

        elif cmd == "/tareas":
            send_telegram(chat_id, handle_tareas(chat_id))

        elif cmd == "/reload":
            old_mtime = _taxonomy_mtime
            old_folders = len(_folder_cache)
            _folder_cache.clear()  # invalidar cache de carpetas
            save_folder_cache()
            load_taxonomy()
            kl = len(_keyword_index)
            fl = len(_folder_cache)
            msg_parts = [f"🔄 Taxonomia recargada: {kl} keywords"]
            if old_folders > 0:
                msg_parts.append(f"Cache de carpetas invalidado (tenias {old_folders})")
            send_telegram(chat_id, " | ".join(msg_parts) + ".", reply_markup=main_keyboard())

        elif cmd == "/stats":
            uptime = ""
            if stats.get("start_time"):
                try:
                    started = datetime.fromisoformat(stats["start_time"])
                    delta = datetime.now() - started
                    h, m = divmod(int(delta.total_seconds()), 3600)
                    m, s = divmod(m, 60)
                    uptime = f"⏱ {h}h {m}m {s}s"
                except Exception:
                    pass
            ac = "activa" if AUTO_CLASSIFY_SECONDS > 0 else "desactivada"
            msg = (
                f"📊 *Estadisticas del bot*\n\n"
                f"• Clasificaciones: *{stats['classified_total']}*\n"
                f"• Movidos: *{stats['moved_total']}*\n"
                f"• Fallidos: *{stats['failed_total']}*\n"
                f"• Llamadas API: *{stats['api_calls']}*\n"
                f"• Auto-clasificar: {ac}"
            )
            if AUTO_CLASSIFY_SECONDS > 0:
                msg += f" (cada {AUTO_CLASSIFY_SECONDS}s)"
            if uptime:
                msg += f"\n• {uptime}"
            if stats.get("last_classify"):
                msg += f"\n• Ultima clasif: {stats['last_classify'][:19].replace('T', ' ')}"
            send_telegram(chat_id, msg, reply_markup=main_keyboard())

        elif cmd == "/adjuntos":
            parts = text.split(" ", 1)
            msg_id = parts[1].strip() if len(parts) > 1 else ""
            if not msg_id:
                mapping = last_results.get(str(chat_id), {})
                if not mapping:
                    send_telegram(chat_id, "Uso: `/adjuntos <nº>` (lanza /hoy o /buscar primero).")
                    return
                send_telegram(chat_id, "Uso: `/adjuntos <nº>` donde nº sale en la última lista.")
                return
            mapping = last_results.get(str(chat_id), {})
            real_id = mapping.get(msg_id, msg_id)  # allow short id or real id
            send_telegram(chat_id, "📎 Descargando adjuntos...")
            atts = get_attachment(real_id)
            if atts is None:
                send_telegram(chat_id, "❌ Error al acceder a los adjuntos.")
            elif not atts:
                send_telegram(chat_id, "Ese mensaje no tiene adjuntos descargables.")
            else:
                os.makedirs(ATTACH_DIR, exist_ok=True)
                filenames = []
                for att in atts:
                    fpath = os.path.join(ATTACH_DIR, att["name"])
                    data = base64.b64decode(att["bytes"])
                    with open(fpath, "wb") as f:
                        f.write(data)
                    filenames.append(f"{att['name']} ({len(data)} bytes)")
                send_telegram(chat_id,
                    "📎 *Adjuntos guardados en el servidor:*\n\n" +
                    "\n".join(f"  • {n}" for n in filenames))

        elif cmd.startswith("/"):
            send_telegram(chat_id, "Comando no reconocido.", reply_markup=main_keyboard())

        else:
            # Intentar interpretar como lenguaje natural
            send_telegram(chat_id, "🤔 Pensando...")
            nl = interpret_nl(text) if LLM_ENABLED else None
            if nl and nl.get("action") != "unknown":
                action = nl["action"]
                params = nl.get("params", {})
                # Sin texto ni params en el log: llevan destinatarios y cuerpos de correo (RGPD)
                log(f"NL interpreted: action={action}")
                if action == "hoy":
                    send_telegram(chat_id, "📬 Buscando...")
                    send_telegram(chat_id, handle_hoy(chat_id))
                elif action == "clasifica":
                    send_telegram(chat_id, "📋 Analizando...")
                    resp = classify_unread(chat_id=chat_id)
                    keyboard = confirm_keyboard("confirm_aplicar") if resp.startswith("📋") else main_keyboard()
                    send_telegram(chat_id, resp, reply_markup=keyboard)
                elif action == "buscar":
                    query = params.get("query", "")
                    if query:
                        send_telegram(chat_id, f"🔍 Buscando \"{query}\"...")
                        send_telegram(chat_id, handle_buscar(chat_id, query), reply_markup=main_keyboard())
                    else:
                        user_state[chat_id] = {"state": "waiting_search"}
                        save_state()
                        send_telegram(chat_id, "🔍 ¿Qué quieres buscar?")
                elif action == "calendario":
                    send_telegram(chat_id, handle_calendar(chat_id))
                elif action == "tareas":
                    send_telegram(chat_id, handle_tareas(chat_id))
                elif action == "enviar":
                    to = params.get("to", "")
                    subj = params.get("subject", "")
                    body_text = params.get("body", "")
                    if to and subj and body_text:
                        user_state[chat_id] = {
                            "state": "waiting_confirm",
                            "to": to,
                            "subject": subj,
                            "body": body_text
                        }
                        save_state()
                        summary = (
                            f"✉️ *Confirmar envio:*\n\n"
                            f"*Para:* {to}\n"
                            f"*Asunto:* {subj}\n"
                            f"*Cuerpo:* {body_text[:200]}"
                        )
                        send_telegram(chat_id, summary, reply_markup=confirm_keyboard("confirm_send"))
                    else:
                        user_state[chat_id] = {"state": "waiting_to"}
                        save_state()
                        send_telegram(chat_id, "✉️ *Enviar correo*\n\nDestinatario (email):")
                elif action == "ver":
                    num = params.get("num", "")
                    if num:
                        body = handle_ver(chat_id, num)
                        send_telegram(chat_id, body, reply_markup=email_actions_keyboard(num))
                    else:
                        send_telegram(chat_id, "¿Qué número de correo quieres leer? Usa /hoy o /buscar primero.")
                elif action == "responder":
                    num = params.get("num", "")
                    reply_text = params.get("text", "")
                    if num and reply_text:
                        mapping = last_results.get(str(chat_id), {})
                        msg_id = mapping.get(str(num))
                        if msg_id:
                            # Lo interpretó un LLM: nunca se envía sin confirmación explícita
                            user_state[chat_id] = {"state": "waiting_confirm_reply",
                                                   "reply_to": msg_id, "text": reply_text}
                            save_state()
                            send_telegram(chat_id,
                                f"↩️ *Confirmar respuesta al nº {num}:*\n\n{reply_text[:300]}",
                                reply_markup=confirm_keyboard("confirm_reply"))
                        else:
                            send_telegram(chat_id, f"No tengo el mensaje nº {num}. Lanza /hoy o /buscar primero.")
                    else:
                        send_telegram(chat_id, "Uso: 'responde al 3 diciendo que mañana a las 10'")
                elif action == "stats":
                    send_telegram(chat_id, "📊 Cargando estadísticas...")
                    handle_message(chat_id, "/stats")  # reuse /stats handler
                    return
                else:
                    send_telegram(chat_id, main_menu_text(), reply_markup=main_keyboard())
            else:
                send_telegram(chat_id,
                    "🤖 No te he entendido. El modelo local esta calentando (primer mensaje tarda ~20s).\n\n"
                    "Prueba otra vez en unos segundos, o usa los comandos con / mientras tanto.",
                    reply_markup=main_keyboard())

    except Exception as e:
        log(f"Message error: {e}")

if __name__ == "__main__":
    main()
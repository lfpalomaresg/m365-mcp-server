#!/usr/bin/env python3
"""Onboarding wizard for new M365 MCP Server clients.

Run once per client to configure Azure App Registration credentials.
Zero external dependencies (stdlib only).

Usage:
    python scripts/setup.py
"""

import os, re, shutil, sys, time, json, urllib.request, urllib.parse, urllib.error, secrets, hashlib, base64, webbrowser
from pathlib import Path

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(APP_DIR, ".env")
ENV_EXAMPLE = os.path.join(APP_DIR, ".env.example")
TOKEN_CACHE_DIR = os.path.expanduser("~/.m365-mcp")

# Deben coincidir EXACTAMENTE con src/auth.ts (test/test_setup_wizard.py lo
# comprueba). Antes el asistente verificaba contra http://localhost y con 7
# permisos, así que su «verificación» no probaba la App Registration real.
REDIRECT_URI = "http://localhost:3000"
SCOPES = [
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
]

# Careo 17/09/2026: lo que el usuario teclea acaba en el .env; un salto de línea
# permitía colar variables (p. ej. TELEGRAM_BOT_TOKEN=...). Formatos admitidos:
_GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def client_id_valido(value):
    return isinstance(value, str) and re.fullmatch(_GUID, value) is not None


def tenant_valido(value):
    if not isinstance(value, str):
        return False
    return (
        value in ("common", "organizations", "consumers")
        or re.fullmatch(_GUID, value) is not None
        # Dominio DNS: etiquetas que empiezan y acaban en alfanumérico.
        or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+", value) is not None
    )


def build_auth_url(client_id, tenant_id, state, code_challenge):
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?{params}"


def build_token_body(client_id, code, code_verifier):
    return urllib.parse.urlencode({
        "client_id": client_id,
        "scope": " ".join(SCOPES),
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }).encode()


def _escribir_privado(path, contenido):
    """Escribe con permisos 0600 (el .env y sus copias llevan secretos)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(contenido)
    os.chmod(path, 0o600)

BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

def banner():
    print(f"""{BOLD}
╔══════════════════════════════════════════╗
║   M365 MCP Server — Client Onboarding   ║
╚══════════════════════════════════════════╝{RESET}
""")

def ask(prompt, default=None):
    d = f" [{default}]" if default else ""
    val = input(f"{BOLD}?{RESET} {prompt}{d}: ").strip()
    return val if val else default

def verify_client_id(client_id, tenant_id):
    """Try PKCE auth with the given CLIENT_ID to verify it works."""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    state = secrets.token_urlsafe(16)
    auth_url = build_auth_url(client_id, tenant_id, state, code_challenge)

    print(f"\n{YELLOW}Opening browser for Microsoft login...{RESET}")
    print(f"If the browser doesn't open, visit:\n  {auth_url}\n")

    webbrowser.open(auth_url)
    redirect = input(f"{BOLD}?{RESET} After login, paste the FULL redirect URL here: ").strip()

    try:
        parsed = urllib.parse.urlparse(redirect)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        returned_state = qs.get("state", [None])[0]

        if not code:
            print(f"{RED}✗ No authorization code found in the URL.{RESET}")
            print(f"  Expected: {REDIRECT_URI}/?code=...&state=...")
            return False
        if returned_state != state:
            print(f"{RED}✗ State mismatch — possible CSRF attack. Aborting.{RESET}")
            return False

        token_data = build_token_body(client_id, code, code_verifier)

        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        req = urllib.request.Request(token_url, data=token_data, headers={
            "Content-Type": "application/x-www-form-urlencoded"
        })
        resp = urllib.request.urlopen(req)
        token_response = json.loads(resp.read())

        if "access_token" in token_response:
            print(f"{GREEN}✓ Authentication successful!{RESET}")
            return True
        else:
            print(f"{RED}✗ No access token received.{RESET}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"{RED}✗ Authentication failed: {e.code}{RESET}")
        try:
            err = json.loads(body)
            print(f"  {err.get('error_description', err.get('error', body))}")
        except Exception:
            print(f"  {body[:200]}")
        return False
    except Exception as e:
        print(f"{RED}✗ Unexpected error: {e}{RESET}")
        return False

def create_env(client_id, tenant_id, overwrite=False):
    """Genera .env desde .env.example.

    No sobrescribe un .env existente salvo `overwrite=True`, y en ese caso deja
    copia en .env.bak (antes se perdía, p. ej., la configuración de Telegram).
    Escribe el TENANT_ID indicado (antes se pedía y se ignoraba).
    """
    if not client_id_valido(client_id):
        print(f"{RED}✗ CLIENT_ID no válido: debe ser un GUID (Azure Portal > App Registrations).{RESET}")
        return False
    if not tenant_valido(tenant_id):
        print(f"{RED}✗ Tenant ID no válido: common, organizations, consumers, un GUID o un dominio.{RESET}")
        return False
    if not os.path.exists(ENV_EXAMPLE):
        print(f"{RED}✗ {ENV_EXAMPLE} not found.{RESET}")
        return False

    if os.path.exists(ENV_FILE):
        if not overwrite:
            print(f"{YELLOW}! {ENV_FILE} ya existe: no se toca.{RESET}")
            return False
        # Copia con fecha: no machaca copias anteriores y la cubre `.env.bak.*`
        # del .gitignore (un `.env.bak` a secas NO estaba ignorado).
        base = f"{ENV_FILE}.bak.{time.strftime('%Y%m%d-%H%M%S')}"
        copia, n = base, 1
        while os.path.exists(copia):  # dos ejecuciones en el mismo segundo
            copia, n = f"{base}-{n}", n + 1
        shutil.copy2(ENV_FILE, copia)
        os.chmod(copia, 0o600)
        print(f"{YELLOW}! Copia del .env anterior en {copia}{RESET}")

    os.makedirs(TOKEN_CACHE_DIR, exist_ok=True)
    token_cache_path = os.path.join(TOKEN_CACHE_DIR, ".token_cache.json")

    with open(ENV_EXAMPLE, "r", encoding="utf-8") as f:
        template = f.read()

    env_content = template.replace("your-client-id-here", client_id)
    env_content = re.sub(r"(?m)^TENANT_ID=.*$", f"TENANT_ID={tenant_id}", env_content)
    env_content = env_content.replace(
        "TOKEN_CACHE_PATH=.token_cache.json",
        f"TOKEN_CACHE_PATH={token_cache_path}"
    )
    env_content = env_content.replace(
        "/Users/your-username/Downloads/m365-mcp",
        os.path.expanduser("~/Downloads/m365-mcp")
    )

    _escribir_privado(ENV_FILE, env_content)

    print(f"{GREEN}✓ Created {ENV_FILE}{RESET}")
    print(f"  Token cache: {token_cache_path}")
    return True

def main():
    banner()

    client_id = ask("Azure App Registration CLIENT_ID (from portal.azure.com)")
    if not client_id:
        print(f"{RED}✗ CLIENT_ID is required. Get it from Azure Portal > App Registrations.{RESET}")
        sys.exit(1)

    if not client_id_valido(client_id):
        print(f"{RED}✗ CLIENT_ID no válido: debe ser un GUID.{RESET}")
        sys.exit(1)

    tenant_id = ask("Tenant ID", "common")
    if not tenant_valido(tenant_id):
        print(f"{RED}✗ Tenant ID no válido: common, organizations, consumers, un GUID o un dominio.{RESET}")
        sys.exit(1)

    # Preguntar ANTES del login (careo 17/09/2026): no tiene sentido autenticarse
    # para acabar sin poder escribir el .env.
    overwrite = False
    if os.path.exists(ENV_FILE):
        resp = ask(f"Ya existe {ENV_FILE}. ¿Sobrescribir? Se guarda copia con fecha (s = sí)", "n")
        overwrite = resp.strip().lower() in ("s", "si", "sí", "y", "yes")
        if not overwrite:
            print(f"{YELLOW}! .env sin cambios.{RESET}")
            sys.exit(0)

    print(f"\n{YELLOW}Verifying CLIENT_ID with Microsoft login...{RESET}")
    if not verify_client_id(client_id, tenant_id):
        print(f"\n{RED}✗ Verification failed. Check:"
              f"\n  1. CLIENT_ID is correct"
              f"\n  2. Redirect URI '{REDIRECT_URI}' is registered in Azure Portal"
              f"\n  3. App Registration has 'Accounts in any organizational directory' enabled{RESET}")
        sys.exit(1)

    print(f"\n{GREEN}✓ CLIENT_ID verified.{RESET} Creating .env...")
    if not create_env(client_id, tenant_id, overwrite=overwrite):
        print(f"{YELLOW}! .env sin cambios.{RESET}")
        sys.exit(1)

    print(f"""
{GREEN}╔═══════════════════════════════════╗
║   Setup complete!                  ║
╚═══════════════════════════════════╝{RESET}

Next steps:
  1. Token cache will be populated on first server start
  2. Add Telegram config to .env if using the bot:
     - TELEGRAM_BOT_TOKEN
     - TELEGRAM_ALLOWED_USER_ID
  3. Start the server: {BOLD}npm start{RESET}
  4. Or in Claude Code/Opencode: add to MCP config

Token cache: {os.path.join(TOKEN_CACHE_DIR, '.token_cache.json')}
""")

if __name__ == "__main__":
    main()
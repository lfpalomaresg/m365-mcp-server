#!/usr/bin/env python3
"""Onboarding wizard for new M365 MCP Server clients.

Run once per client to configure Azure App Registration credentials.
Zero external dependencies (stdlib only).

Usage:
    python scripts/setup.py
"""

import os, sys, json, urllib.request, urllib.parse, urllib.error, secrets, hashlib, base64, webbrowser
from pathlib import Path

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(APP_DIR, ".env")
ENV_EXAMPLE = os.path.join(APP_DIR, ".env.example")
TOKEN_CACHE_DIR = os.path.expanduser("~/.m365-mcp")

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
    redirect_uri = "http://localhost"
    scopes = ["offline_access", "User.Read", "Mail.ReadWrite", "Mail.Send",
              "Files.ReadWrite", "Calendars.ReadWrite", "Tasks.ReadWrite"]
    scope = " ".join(scopes)

    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    state = secrets.token_urlsafe(16)
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?{params}"

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
            print(f"  Expected: http://localhost/?code=...&state=...")
            return False
        if returned_state != state:
            print(f"{RED}✗ State mismatch — possible CSRF attack. Aborting.{RESET}")
            return False

        token_data = urllib.parse.urlencode({
            "client_id": client_id,
            "scope": scope,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }).encode()

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

def create_env(client_id, tenant_id):
    if not os.path.exists(ENV_EXAMPLE):
        print(f"{RED}✗ {ENV_EXAMPLE} not found.{RESET}")
        return False

    os.makedirs(TOKEN_CACHE_DIR, exist_ok=True)
    token_cache_path = os.path.join(TOKEN_CACHE_DIR, ".token_cache.json")

    with open(ENV_EXAMPLE, "r") as f:
        template = f.read()

    env_content = template.replace("your-client-id-here", client_id)
    env_content = env_content.replace(
        "TOKEN_CACHE_PATH=.token_cache.json",
        f"TOKEN_CACHE_PATH={token_cache_path}"
    )
    env_content = env_content.replace(
        "/Users/your-username/Downloads/m365-mcp",
        os.path.expanduser("~/Downloads/m365-mcp")
    )

    with open(ENV_FILE, "w") as f:
        f.write(env_content)

    print(f"{GREEN}✓ Created {ENV_FILE}{RESET}")
    print(f"  Token cache: {token_cache_path}")
    return True

def main():
    banner()

    client_id = ask("Azure App Registration CLIENT_ID (from portal.azure.com)")
    if not client_id:
        print(f"{RED}✗ CLIENT_ID is required. Get it from Azure Portal > App Registrations.{RESET}")
        sys.exit(1)

    tenant_id = ask("Tenant ID", "common")

    print(f"\n{YELLOW}Verifying CLIENT_ID with Microsoft login...{RESET}")
    if not verify_client_id(client_id, tenant_id):
        print(f"\n{RED}✗ Verification failed. Check:"
              f"\n  1. CLIENT_ID is correct"
              f"\n  2. Redirect URI 'http://localhost' is registered in Azure Portal"
              f"\n  3. App Registration has 'Accounts in any organizational directory' enabled{RESET}")
        sys.exit(1)

    print(f"\n{GREEN}✓ CLIENT_ID verified.{RESET} Creating .env...")
    create_env(client_id, tenant_id)

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
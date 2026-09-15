#!/usr/bin/env bash
# startup.sh — Arranque de sesión (funciona con cualquier IA o manualmente)
#
# Uso: ./startup.sh
#   o desde una IA: ejecuta este script al iniciar sesión
#
# Qué hace:
#   1. Carga BW_SESSION desde el credential store del SO
#   2. cd al repo y git pull
#   3. env-sync.sh pull (trae .env desde Bitwarden)
#   4. Reporta estado en formato claro (AI-friendly + human-friendly)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$HOME/MAIN_PROYECTOS/m365-mcp-server"
ENV_SYNC="$REPO_DIR/scripts/env-sync.sh"
CRED_STORE_WIN="$SCRIPT_DIR/cred-store.ps1"
CRED_STORE_MAC="$REPO_DIR/scripts/cred-store.sh"

# ─── 1. Cargar BW_SESSION ────────────────────────────────────────────────────
BW_SESSION=""
if command -v powershell &>/dev/null && [ -f "$CRED_STORE_WIN" ]; then
  BW_SESSION=$(powershell -ExecutionPolicy Bypass -File "$CRED_STORE_WIN" get 2>/dev/null || true)
elif [ -x "$CRED_STORE_MAC" ]; then
  BW_SESSION=$("$CRED_STORE_MAC" get 2>/dev/null || true)
fi

if [ -n "$BW_SESSION" ]; then
  export BW_SESSION
  echo "startup: BW_SESSION cargada ✓"
else
  echo "startup: ⚠ BW_SESSION no disponible (vault bloqueado o sin setup)"
  echo "startup:   el sync se hará solo si hay sesión activa"
fi

# ─── 2. cd al repo ───────────────────────────────────────────────────────────
if [ ! -d "$REPO_DIR" ]; then
  echo "startup: ✗ no existe $REPO_DIR — saltando sync"
  exit 0
fi
cd "$REPO_DIR"

# ─── 3. Git pull ─────────────────────────────────────────────────────────────
echo "startup: git pull..."
if git pull 2>&1; then
  echo "startup: git pull ✓"
else
  echo "startup: ⚠ git pull falló (¿sin conexión?) — continuando"
fi

# ─── 4. Env-sync pull ────────────────────────────────────────────────────────
if [ -x "$ENV_SYNC" ]; then
  echo "startup: env-sync pull..."
  if "$ENV_SYNC" pull 2>&1; then
    echo "startup: env-sync pull ✓"
  else
    echo "startup: ⚠ env-sync pull falló (vault bloqueado o sin conexión)"
  fi
  echo "startup: env-sync diff..."
  "$ENV_SYNC" diff 2>&1 || true
else
  echo "startup: ✗ no existe $ENV_SYNC"
fi

echo "startup: ✓ listo"
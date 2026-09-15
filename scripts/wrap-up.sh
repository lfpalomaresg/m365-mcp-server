#!/usr/bin/env bash
# wrap-up.sh — Cierre de sesión (funciona con cualquier IA o manualmente)
#
# Uso: ./wrap-up.sh
#   o desde una IA: ejecuta este script al cerrar sesión
#
# Qué hace:
#   1. Carga BW_SESSION desde el credential store del SO
#   2. cd al repo
#   3. env-sync.sh diff contra el vault
#   4. Si hay diferencias → env-sync.sh push (sube .env local al vault)
#   5. Sugiere registrar tareas pendientes
#
# Comportamiento:
#   - push automático si hay diferencias (desatendido)
#   - si falla por vault bloqueado, avisa y termina

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
  echo "wrap-up: BW_SESSION cargada ✓"
else
  echo "wrap-up: ⚠ BW_SESSION no disponible — no se puede hacer push"
  echo "wrap-up:   corre 'bw unlock --raw' y guarda la clave en el credential store"
  echo "wrap-up:   o ejecuta ./scripts/env-sync.sh push manualmente"
  exit 1
fi

# ─── 2. cd al repo ───────────────────────────────────────────────────────────
if [ ! -d "$REPO_DIR" ]; then
  echo "wrap-up: ✗ no existe $REPO_DIR — saltando"
  exit 0
fi
cd "$REPO_DIR"

# ─── 3. Env-sync push si hay cambios ─────────────────────────────────────────
if [ ! -x "$ENV_SYNC" ]; then
  echo "wrap-up: ✗ no existe $ENV_SYNC"
  exit 1
fi

echo "wrap-up: comprobando si .env cambió..."
if "$ENV_SYNC" diff 2>&1 | grep -q '^env-sync: idénticos$'; then
  echo "wrap-up: .env sincronizado — no hace falta push ✓"
else
  echo "wrap-up: .env diferente → haciendo push..."
  if "$ENV_SYNC" push 2>&1; then
    echo "wrap-up: push ✓ — Mac recibirá los cambios al hacer git pull"
  else
    echo "wrap-up: ✗ push falló"
    exit 1
  fi
fi

# ─── 4. Recordatorio de tareas pendientes ─────────────────────────────────────
echo ""
echo "wrap-up: ───────────────────────────────────────────────"
echo "wrap-up:   Si quedan tareas pendientes, apúntalas en:"
echo "wrap-up:     G:\Mi unidad\claude_workspace\AI_OS\PENDING_HP.md"
echo "wrap-up:   O dile a tu IA que ejecute el meta-wrap-up"
echo "wrap-up: ───────────────────────────────────────────────"
echo "wrap-up: ✓ sesión cerrada"
#!/usr/bin/env bash
# cred-store.sh — guarda/recupera BW_SESSION en el Keychain de macOS
# Dependencia: `security` (built-in en macOS)
#
#   ./scripts/cred-store.sh set <session_key>   # guarda
#   ./scripts/cred-store.sh get                 # recupera (stdout)
#   ./scripts/cred-store.sh delete             # borra

set -euo pipefail
SERVICE="com.luisfran.m365-mcp-server"   # nombre de la entrada ya creada en el Keychain del Mac (15/09)
ACCOUNT="bw-session-env-sync"

case "${1:-}" in
  set)
    [ -z "${2:-}" ] && { echo "falta la session key" >&2; exit 1; }
    security add-generic-password -s "$SERVICE" -a "$ACCOUNT" -w "$2"
    echo "OK: BW_SESSION guardada en Keychain de macOS"
    ;;
  get)
    security find-generic-password -s "$SERVICE" -a "$ACCOUNT" -w 2>/dev/null
    ;;
  delete)
    security delete-generic-password -s "$SERVICE" -a "$ACCOUNT" 2>/dev/null || true
    echo "OK: borrada del Keychain"
    ;;
  *)
    echo "uso: $0 {set|get|delete}" >&2; exit 2
    ;;
esac
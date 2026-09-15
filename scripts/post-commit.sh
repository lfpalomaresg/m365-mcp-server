#!/usr/bin/env bash
# post-commit para macOS: si .env cambió, hace env-sync push automático
# Instalación: ln -sf ../../scripts/env-sync.sh .git/hooks/post-commit
# O copiar este script a .git/hooks/post-commit y hacer chmod +x

set -euo pipefail
cd "$(git rev-parse --git-dir)/.." || exit 1

# Solo ejecutar si ..env cambió en el commit
if git diff --cached --name-only HEAD~1..HEAD 2>/dev/null | grep -q '^\.env$'; then
  [ -x scripts/cred-store.sh ] && BW_SESSION=$(scripts/cred-store.sh get) && export BW_SESSION
  [ -x scripts/env-sync.sh ] && ./scripts/env-sync.sh push
fi
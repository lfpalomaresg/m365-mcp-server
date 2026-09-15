#!/usr/bin/env bash
# env-sync — sincroniza el .env entre el Mac y el HP usando Bitwarden como canal.
#
#   ./scripts/env-sync.sh pull    # vault  -> .env local (hace copia de seguridad antes)
#   ./scripts/env-sync.sh push    # .env local -> vault
#   ./scripts/env-sync.sh diff    # compara los dos, sin escribir nada
#   ./scripts/env-sync.sh status  # estado del vault y del item
#
# Funciona en macOS y en Windows con Git Bash. Solo necesita `bw` y `node`.
#
# Por qué existe: hasta 2026-09-15 los secretos viajaban como .env en claro
# dentro de Google Drive. Se retiró de ahí. Nada de este flujo escribe
# secretos en Drive ni en git — .env sigue en .gitignore.

set -euo pipefail

ITEM_NAME="${ENV_SYNC_ITEM:-m365-mcp-server/.env}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_SYNC_FILE:-$REPO_ROOT/.env}"

die() { printf 'env-sync: %s\n' "$*" >&2; exit 1; }
info() { printf 'env-sync: %s\n' "$*" >&2; }

command -v bw   >/dev/null 2>&1 || die "falta el CLI de Bitwarden — instálalo con: npm install -g @bitwarden/cli"
command -v node >/dev/null 2>&1 || die "falta node"

# --- sesión del vault -------------------------------------------------------

ensure_session() {
  local state
  state="$(bw status 2>/dev/null | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{process.stdout.write(JSON.parse(s).status||"")}catch{process.stdout.write("")}})')"

  case "$state" in
    unlocked) : ;;
    locked|"")
      info "el vault está bloqueado — introduce tu contraseña maestra"
      BW_SESSION="$(bw unlock --raw)"
      export BW_SESSION
      [ -n "$BW_SESSION" ] || die "no se pudo desbloquear el vault"
      ;;
    unauthenticated)
      die "no has iniciado sesión en Bitwarden — ejecuta primero: bw login"
      ;;
    *) die "estado del vault no reconocido: $state" ;;
  esac
}

# --- lectura/escritura del item --------------------------------------------

# Devuelve el JSON del item, o cadena vacía si no existe todavía.
fetch_item() {
  bw get item "$ITEM_NAME" 2>/dev/null || true
}

json_field() {
  # uso: json_field <campo>   (lee el JSON por stdin)
  node -e '
    let s = "";
    process.stdin.on("data", d => s += d).on("end", () => {
      try {
        const item = JSON.parse(s);
        process.stdout.write(String(item[process.argv[1]] ?? ""));
      } catch { process.stdout.write(""); }
    });
  ' "$1"
}

vault_contents() {
  local json
  json="$(fetch_item)"
  [ -n "$json" ] || return 1
  printf '%s' "$json" | json_field notes
}

# --- comandos ---------------------------------------------------------------

cmd_status() {
  ensure_session
  bw sync >/dev/null 2>&1 || true
  printf 'item:     %s\n' "$ITEM_NAME"
  printf 'fichero:  %s\n' "$ENV_FILE"
  if [ -f "$ENV_FILE" ]; then
    printf 'local:    %s líneas\n' "$(grep -c '' "$ENV_FILE" || echo 0)"
  else
    printf 'local:    (no existe)\n'
  fi
  if vault_contents >/dev/null 2>&1; then
    printf 'vault:    %s líneas\n' "$(vault_contents | grep -c '' || echo 0)"
  else
    printf 'vault:    (el item no existe todavía — usa "push")\n'
  fi
}

cmd_pull() {
  ensure_session
  bw sync >/dev/null 2>&1 || true

  local contents
  contents="$(vault_contents)" || die "el item «$ITEM_NAME» no existe en el vault. Ejecuta \"push\" desde el equipo que sí tiene el .env bueno."
  [ -n "$contents" ] || die "el item «$ITEM_NAME» está vacío — no sobrescribo nada"

  if [ -f "$ENV_FILE" ]; then
    local backup="$ENV_FILE.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$ENV_FILE" "$backup"
    info "copia de seguridad: $backup"
  fi

  umask 077
  printf '%s\n' "$contents" > "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  info "escrito $ENV_FILE ($(grep -c '' "$ENV_FILE") líneas)"
}

cmd_push() {
  [ -f "$ENV_FILE" ] || die "no existe $ENV_FILE — nada que subir"
  ensure_session
  bw sync >/dev/null 2>&1 || true

  local contents json id payload
  contents="$(cat "$ENV_FILE")"
  [ -n "$contents" ] || die "$ENV_FILE está vacío — no subo nada"

  json="$(fetch_item)"
  id="$(printf '%s' "$json" | json_field id)"

  payload="$(ENV_SYNC_BODY="$contents" ENV_SYNC_NAME="$ITEM_NAME" ENV_SYNC_ID="$id" node -e '
    const id = process.env.ENV_SYNC_ID || "";
    const item = {
      type: 2,
      name: process.env.ENV_SYNC_NAME,
      notes: process.env.ENV_SYNC_BODY,
      secureNote: { type: 0 },
      favorite: false,
    };
    if (id) item.id = id;
    process.stdout.write(JSON.stringify(item));
  ')"

  if [ -n "$id" ]; then
    printf '%s' "$payload" | bw encode | bw edit item "$id" >/dev/null
    info "item actualizado en el vault ($ITEM_NAME)"
  else
    printf '%s' "$payload" | bw encode | bw create item >/dev/null
    info "item creado en el vault ($ITEM_NAME)"
  fi
  bw sync >/dev/null 2>&1 || true
}

cmd_diff() {
  ensure_session
  bw sync >/dev/null 2>&1 || true

  # Deliberadamente NO son 'local': el trap EXIT se dispara cuando la funcion
  # ya salio de ambito y con 'set -u' fallaria, dejando en /tmp ficheros
  # temporales con el contenido del .env en claro.
  tmp_vault="$(mktemp)"; tmp_local="$(mktemp)"
  trap 'rm -f "${tmp_vault:-}" "${tmp_local:-}"' EXIT

  vault_contents > "$tmp_vault" 2>/dev/null || die "el item «$ITEM_NAME» no existe en el vault"
  if [ -f "$ENV_FILE" ]; then cat "$ENV_FILE" > "$tmp_local"; fi

  # Compara solo los NOMBRES de variable, nunca los valores, para no
  # volcar secretos en pantalla ni en los logs del terminal.
  local only_vault only_local
  only_vault="$(comm -23 <(grep -o '^[A-Za-z_][A-Za-z0-9_]*=' "$tmp_vault" | sort -u) <(grep -o '^[A-Za-z_][A-Za-z0-9_]*=' "$tmp_local" | sort -u) || true)"
  only_local="$(comm -13 <(grep -o '^[A-Za-z_][A-Za-z0-9_]*=' "$tmp_vault" | sort -u) <(grep -o '^[A-Za-z_][A-Za-z0-9_]*=' "$tmp_local" | sort -u) || true)"

  if cmp -s "$tmp_vault" "$tmp_local"; then
    info "idénticos"
    return 0
  fi

  info "hay diferencias:"
  [ -n "$only_vault" ] && printf '  solo en el vault: %s\n' "$(printf '%s' "$only_vault" | tr '\n' ' ')"
  [ -n "$only_local" ] && printf '  solo en local:    %s\n' "$(printf '%s' "$only_local" | tr '\n' ' ')"
  [ -z "$only_vault$only_local" ] && printf '  mismas variables, distintos valores\n'
  return 1
}

case "${1:-}" in
  pull)   cmd_pull ;;
  push)   cmd_push ;;
  diff)   cmd_diff ;;
  status) cmd_status ;;
  *)
    cat >&2 <<'USAGE'
env-sync — sincroniza el .env entre equipos vía Bitwarden

  ./scripts/env-sync.sh pull     vault -> .env local (con copia de seguridad)
  ./scripts/env-sync.sh push     .env local -> vault
  ./scripts/env-sync.sh diff     compara nombres de variable, sin mostrar valores
  ./scripts/env-sync.sh status   estado del vault y del item

Variables opcionales:
  ENV_SYNC_ITEM   nombre del item en Bitwarden (por defecto: m365-mcp-server/.env)
  ENV_SYNC_FILE   ruta del .env (por defecto: la raíz del repo)
USAGE
    exit 2
    ;;
esac

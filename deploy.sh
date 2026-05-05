#!/usr/bin/env bash
# =============================================================================
# nano-vm-demo — VPS deploy script
# Tested: Ubuntu 22.04 / 24.04, Debian 12
# Usage:  chmod +x deploy.sh && ./deploy.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$REPO_DIR/.env"
ENV_EXAMPLE="$REPO_DIR/.env.example"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; RESET='\033[0m'; BOLD='\033[1m'

log()  { echo -e "${CYAN}[nano-vm]${RESET} $*"; }
ok()   { echo -e "${GREEN}[  ok  ]${RESET} $*"; }
warn() { echo -e "${YELLOW}[ warn ]${RESET} $*"; }
err()  { echo -e "${RED}[ err  ]${RESET} $*" >&2; exit 1; }

# ── banner ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
cat <<'BANNER'
  _ __   __ _ _ __   ___        __   ___ __ ___
 | '_ \ / _` | '_ \ / _ \ ___  \ \ / / '_ ` _ \
 | | | | (_| | | | | (_) |___   \ V /| | | | | |
 |_| |_|\__,_|_| |_|\___/        \_/ |_| |_| |_|
  deterministic ai execution — demo stack
BANNER
echo -e "${RESET}"

cd "$REPO_DIR"

# ── 1. docker ─────────────────────────────────────────────────────────────────
log "Checking Docker..."
if ! command -v docker &>/dev/null; then
  warn "Docker not found — installing via get.docker.com"
  curl -fsSL https://get.docker.com | sh
  ok "Docker installed: $(docker --version)"
else
  ok "Docker: $(docker --version)"
fi

# ── 2. compose plugin ─────────────────────────────────────────────────────────
log "Checking Docker Compose plugin..."
if ! docker compose version &>/dev/null 2>&1; then
  warn "Compose plugin missing — installing v2.27.0"
  DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker}"
  mkdir -p "$DOCKER_CONFIG/cli-plugins"
  ARCH="$(uname -m)"
  [[ "$ARCH" == "aarch64" ]] && ARCH="aarch64" || ARCH="x86_64"
  curl -SL "https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-${ARCH}" \
    -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
  chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"
fi
ok "Compose: $(docker compose version)"

# ── 3. .env ───────────────────────────────────────────────────────────────────
log "Checking .env..."
if [ ! -f "$ENV_FILE" ]; then
  [ -f "$ENV_EXAMPLE" ] || err ".env.example not found in $REPO_DIR"
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  warn ".env created from .env.example"
  echo ""
  echo -e "  Edit ${YELLOW}$ENV_FILE${RESET} to configure BOT_TOKEN, DOMAIN, etc."
  echo ""
  read -rp "  Continue with defaults (DEMO_MODE=true, HTTP only)? [y/N] " CONT
  [[ "${CONT,,}" == "y" ]] || { echo "Edit .env and re-run deploy.sh"; exit 0; }
else
  ok ".env found"
fi

set -a; source "$ENV_FILE"; set +a
PORT="${PORT:-8080}"
DOMAIN="${DOMAIN:-}"
USE_HTTPS=false

# ── 4. HTTPS mode ─────────────────────────────────────────────────────────────
if [ -n "$DOMAIN" ]; then
  ACME_EMAIL="${ACME_EMAIL:-}"
  if [ -z "$ACME_EMAIL" ]; then
    warn "DOMAIN is set but ACME_EMAIL is empty — skipping HTTPS"
  else
    echo ""
    echo -e "  Domain detected: ${CYAN}${DOMAIN}${RESET}"
    read -rp "  Enable automatic HTTPS via Caddy? [Y/n] " HTTPS_CHOICE
    if [[ "${HTTPS_CHOICE,,}" != "n" ]]; then
      USE_HTTPS=true
      ok "HTTPS mode enabled — Caddy will obtain a Let's Encrypt cert"
    fi
  fi
fi

# ── 5. firewall ───────────────────────────────────────────────────────────────
log "Configuring firewall..."
open_port() {
  local p="$1"
  if command -v ufw &>/dev/null && ufw status | grep -qw active; then
    ufw allow "$p/tcp" &>/dev/null || true
    ok "ufw: port $p allowed"
  elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port="$p/tcp" &>/dev/null || true
    firewall-cmd --reload &>/dev/null || true
    ok "firewalld: port $p allowed"
  fi
}

if [ "$USE_HTTPS" = true ]; then
  open_port 80
  open_port 443
else
  open_port "$PORT"
fi

# ── 6. stop old containers ────────────────────────────────────────────────────
log "Stopping old containers..."
docker compose --profile https down --remove-orphans 2>/dev/null || true
ok "Stopped"

# ── 7. build ──────────────────────────────────────────────────────────────────
log "Building images (this takes ~60s on first run)..."
if [ "$USE_HTTPS" = true ]; then
  docker compose --profile https build --no-cache
else
  docker compose build --no-cache
fi
ok "Build complete"

# ── 8. start ──────────────────────────────────────────────────────────────────
log "Starting services..."
if [ "$USE_HTTPS" = true ]; then
  docker compose --profile https up -d
else
  docker compose up -d
fi

# ── 9. wait for backend health ────────────────────────────────────────────────
log "Waiting for backend..."
MAX=45; N=0
until docker compose exec -T backend \
    python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    &>/dev/null 2>&1; do
  N=$((N+1))
  [ "$N" -ge "$MAX" ] && err "Backend not healthy after ${MAX}s. Check: docker compose logs backend"
  printf "."; sleep 1
done
echo ""
ok "Backend healthy"

# ── 10. smoke test ────────────────────────────────────────────────────────────
log "Running API smoke test..."
BASE="http://localhost:${PORT}"
HTTP_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null || echo '000')"
if [ "$HTTP_STATUS" = "200" ]; then
  ok "GET /health → 200"
else
  warn "GET /health → $HTTP_STATUS (may need a moment for nginx to start)"
fi

TAROT_STATUS="$(curl -s -o /dev/null -w '%{http_code}' \
  -X POST "$BASE/api/tarot" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Anna","dob":"12.05.1990","color":"blue","question":"Test"}' \
  2>/dev/null || echo '000')"
if [ "$TAROT_STATUS" = "200" ]; then
  ok "POST /api/tarot → 200"
else
  warn "POST /api/tarot → $TAROT_STATUS"
fi

# ── 11. summary ───────────────────────────────────────────────────────────────
PUBLIC_IP="$(curl -s --max-time 5 ifconfig.me 2>/dev/null \
  || curl -s --max-time 5 api.ipify.org 2>/dev/null \
  || echo '<server-ip>')"

echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  nano-vm demo is running${RESET}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
if [ "$USE_HTTPS" = true ]; then
  echo -e "  Landing:   ${CYAN}https://${DOMAIN}${RESET}"
  echo -e "  API:       ${CYAN}https://${DOMAIN}/api/tarot${RESET}"
else
  echo -e "  Landing:   ${CYAN}http://${PUBLIC_IP}:${PORT}${RESET}"
  echo -e "  API:       ${CYAN}http://${PUBLIC_IP}:${PORT}/api/tarot${RESET}"
  echo -e "  Health:    ${CYAN}http://${PUBLIC_IP}:${PORT}/health${RESET}"
fi
echo ""
echo -e "  Logs:      ${YELLOW}docker compose logs -f${RESET}"
echo -e "  Stop:      ${YELLOW}docker compose down${RESET}  (or: make down)"
echo -e "  Restart:   ${YELLOW}docker compose restart backend${RESET}"
echo ""
BOT_TOKEN_VAL="${BOT_TOKEN:-}"
if [ -z "$BOT_TOKEN_VAL" ]; then
  warn "BOT_TOKEN not set — Telegram bot disabled."
  warn "Set BOT_TOKEN in .env, then: docker compose restart backend"
else
  ok "Telegram bot polling active"
fi
echo ""

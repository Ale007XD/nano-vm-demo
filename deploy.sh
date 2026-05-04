#!/usr/bin/env bash
# =============================================================================
# nano-vm-demo — VPS deploy script
# Tested on: Ubuntu 22.04 / 24.04, Debian 12
# Usage:
#   chmod +x deploy.sh && ./deploy.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$REPO_DIR/docker-compose.yml"
ENV_FILE="$REPO_DIR/.env"
ENV_EXAMPLE="$REPO_DIR/.env.example"

# ── colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; RESET='\033[0m'; BOLD='\033[1m'

log()  { echo -e "${CYAN}[nano-vm]${RESET} $*"; }
ok()   { echo -e "${GREEN}[  ok  ]${RESET} $*"; }
warn() { echo -e "${YELLOW}[ warn ]${RESET} $*"; }
err()  { echo -e "${RED}[ err  ]${RESET} $*"; exit 1; }

# ── banner ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
cat <<'EOF'
  _ __   __ _ _ __   ___        __   ___ __ ___
 | '_ \ / _` | '_ \ / _ \ ___  \ \ / / '_ ` _ \
 | | | | (_| | | | | (_) |___   \ V /| | | | | |
 |_| |_|\__,_|_| |_|\___/        \_/ |_| |_| |_|

  deterministic ai execution — demo stack
EOF
echo -e "${RESET}"

# ── 1. check / install docker ─────────────────────────────────────────────────
log "Checking Docker..."
if ! command -v docker &>/dev/null; then
  warn "Docker not found — installing..."
  curl -fsSL https://get.docker.com | sh
  ok "Docker installed: $(docker --version)"
else
  ok "Docker: $(docker --version)"
fi

# ── 2. check / install docker compose plugin ──────────────────────────────────
log "Checking Docker Compose..."
if ! docker compose version &>/dev/null 2>&1; then
  warn "Docker Compose plugin not found — installing..."
  DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker}"
  mkdir -p "$DOCKER_CONFIG/cli-plugins"
  COMPOSE_VERSION="v2.27.0"
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64)  ARCH="x86_64" ;;
    aarch64) ARCH="aarch64" ;;
    *)        err "Unsupported arch: $ARCH" ;;
  esac
  curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${ARCH}" \
    -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
  chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"
  ok "Docker Compose: $(docker compose version)"
else
  ok "Docker Compose: $(docker compose version)"
fi

# ── 3. .env setup ─────────────────────────────────────────────────────────────
log "Checking .env..."
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    warn ".env created from .env.example"
    warn "Edit $ENV_FILE to set BOT_TOKEN and other variables, then re-run this script."
    echo ""
    echo -e "  ${YELLOW}nano $ENV_FILE${RESET}"
    echo ""
    read -rp "Continue with current .env (DEMO_MODE=true, no bot token)? [y/N] " CONT
    [[ "${CONT,,}" == "y" ]] || exit 0
  else
    err ".env.example not found in $REPO_DIR"
  fi
else
  ok ".env found"
fi

# source for PORT variable
set -a; source "$ENV_FILE"; set +a
PORT="${PORT:-8080}"

# ── 4. open firewall port ──────────────────────────────────────────────────────
log "Checking firewall for port $PORT..."
if command -v ufw &>/dev/null; then
  if ufw status | grep -qw active; then
    ufw allow "$PORT/tcp" &>/dev/null || true
    ok "ufw: port $PORT allowed"
  fi
elif command -v firewall-cmd &>/dev/null; then
  firewall-cmd --permanent --add-port="$PORT/tcp" &>/dev/null || true
  firewall-cmd --reload &>/dev/null || true
  ok "firewalld: port $PORT allowed"
fi

# ── 5. stop old containers ────────────────────────────────────────────────────
log "Stopping existing containers (if any)..."
cd "$REPO_DIR"
docker compose down --remove-orphans 2>/dev/null || true
ok "Stopped"

# ── 6. build & start ──────────────────────────────────────────────────────────
log "Building images..."
docker compose build --no-cache

log "Starting services..."
docker compose up -d

# ── 7. health check ───────────────────────────────────────────────────────────
log "Waiting for backend health check..."
MAX=30; COUNT=0
until docker compose exec -T backend \
      python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
      &>/dev/null; do
  COUNT=$((COUNT+1))
  if [ "$COUNT" -ge "$MAX" ]; then
    err "Backend did not become healthy after ${MAX}s. Run: docker compose logs backend"
  fi
  sleep 1
  printf "."
done
echo ""
ok "Backend healthy"

# ── 8. get public IP ──────────────────────────────────────────────────────────
PUBLIC_IP="$(curl -s --max-time 5 ifconfig.me || curl -s --max-time 5 api.ipify.org || echo '<your-server-ip>')"

# ── 9. done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  nano-vm demo is running${RESET}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  Landing:   ${CYAN}http://${PUBLIC_IP}:${PORT}${RESET}"
echo -e "  API:       ${CYAN}http://${PUBLIC_IP}:${PORT}/api/tarot${RESET}"
echo -e "  Health:    ${CYAN}http://${PUBLIC_IP}:${PORT}/health${RESET}"
echo ""
echo -e "  Logs:      ${YELLOW}docker compose logs -f${RESET}"
echo -e "  Stop:      ${YELLOW}docker compose down${RESET}"
echo -e "  Restart:   ${YELLOW}docker compose restart${RESET}"
echo ""

BOT_TOKEN_SET="${BOT_TOKEN:-}"
if [ -z "$BOT_TOKEN_SET" ]; then
  warn "BOT_TOKEN not set — Telegram bot polling is disabled."
  warn "Set BOT_TOKEN in .env and run: docker compose restart backend"
else
  ok "Telegram bot polling active"
fi
echo ""

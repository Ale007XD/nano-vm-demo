# nano-vm-demo

Lightweight demo stand for **nano-vm** — deterministic AI execution runtime.

Interactive landing + Telegram bot. Single `docker compose up` deployment.

---

## What it demonstrates

| Property | How |
|---|---|
| **Reproducibility** | Same input → same hash, always. Run twice, get `✓ MATCH`. |
| **Tamper detection** | Change one character in `name` → hash diverges, diff shows the cause. |
| **Full trace** | Every step (`local` / `llm`) is recorded with duration and output. |
| **LLM caching** | `llm_interpret` step is served from cache on repeat runs (<10ms, $0.00). |

Demo scenario: tarot reading. Mystical interface, strict engineering underneath.

---

## Quick start (VPS)

```bash
git clone https://github.com/your-org/nano-vm-demo.git
cd nano-vm-demo
chmod +x deploy.sh
./deploy.sh
```

The script:
1. Installs Docker + Compose if missing
2. Creates `.env` from `.env.example` if missing
3. Opens the firewall port
4. Builds and starts both containers
5. Runs health check and prints the URL

**Requirements:** Ubuntu 22.04+ / Debian 12, 1+ vCPU, 512 MB RAM minimum.

---

## Configuration

Copy `.env.example` → `.env` and edit:

```env
# Telegram bot token (optional — landing works without it)
BOT_TOKEN=123456:ABC-DEF...

# Demo mode (true = mock LLM, no API keys needed)
DEMO_MODE=true

# Real LLM (only needed when DEMO_MODE=false)
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...

# Port (default 8080)
PORT=8080
```

After editing:
```bash
docker compose restart
```

---

## Architecture

```
                  ┌──────────────┐
browser/telegram  │   nginx :80  │ ← port 8080 on host
                  │  (frontend)  │
                  └──────┬───────┘
                         │ /api/*
                  ┌──────▼───────┐
                  │  FastAPI     │  ← /api/tarot
                  │  + aiogram   │  ← Telegram polling
                  │  (backend)   │
                  └──────────────┘
```

**Backend** (`backend/`):
- `main.py` — FastAPI + aiogram in one process
- `agent.py` — deterministic program executor with LLM cache
- `programs/tarot_profile.py` — step graph definition
- `tools/` — seed, cards, llm_interpret, respond

**Frontend** (`frontend/`):
- `html/index.html` — static landing, Terminal.ini style
- `nginx.conf` — serves static + proxies `/api/*`

---

## API

### `POST /api/tarot`
```json
{
  "name": "Anna",
  "dob": "12.05.1990",
  "color": "blue",
  "question": "Is relocation the right move?"
}
```

Response:
```json
{
  "run_id": "0xA1B2C3D4",
  "hash": "9b2c4d6e8f1a3c22",
  "duration_ms": 95,
  "steps": [
    {"id": "generate_seed", "type": "local", "status": "ok", "duration_ms": 38, "detail": "seed=0x8F2A1C"},
    {"id": "draw_cards",    "type": "local", "status": "ok", "duration_ms": 24, "detail": "The Fool, Justice, The Star"},
    {"id": "llm_interpret", "type": "llm",   "status": "ok", "duration_ms": 8,  "detail": "(cached) deterministic"},
    {"id": "respond",       "type": "local", "status": "ok", "duration_ms": 9,  "detail": "output sent"}
  ],
  "output": "The cards suggest...",
  "diff": null
}
```

### `POST /api/repeat`
```json
{ "run_id": "0xA1B2C3D4" }
```
Returns same shape. If hash matches → `"diff": null`. If diverged → diff object.

### `GET /health`
```json
{ "status": "ok", "demo_mode": true }
```

---

## Telegram bot

Commands:
```
/start   — welcome message
/tarot   <name> | <dob> | <color> | <question>
```

Example:
```
/tarot Anna | 12.05.1990 | blue | Is relocation the right move?
```

Response includes full HTML-formatted trace with step timings and hash.

---

## Roadmap

- [ ] `nano-vm-mcp` sidecar — migrate `deep_research` tool to MCP
- [ ] `nano-vm-vault` integration — `privacy_shield` noise map → vault
- [ ] Redis LLM cache — persist across restarts
- [ ] HTTPS via Caddy sidecar

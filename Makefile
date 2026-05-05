# nano-vm-demo Makefile
# Usage: make <target>

.PHONY: help up down restart logs test lint build clean https

# ── default ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  nano-vm-demo — available targets"
	@echo ""
	@echo "  make up        start stack (HTTP, port 8080)"
	@echo "  make https     start stack with Caddy HTTPS (needs DOMAIN in .env)"
	@echo "  make down      stop all containers"
	@echo "  make restart   restart backend only"
	@echo "  make logs      tail all logs"
	@echo "  make logs-be   tail backend logs"
	@echo "  make test      run pytest suite (no docker needed)"
	@echo "  make lint      ruff check backend/"
	@echo "  make build     rebuild images without cache"
	@echo "  make clean     down + remove volumes"
	@echo ""

# ── stack control ─────────────────────────────────────────────────────────────
up:
	docker compose up -d

https:
	docker compose --profile https up -d

down:
	docker compose --profile https down

restart:
	docker compose restart backend

logs:
	docker compose logs -f

logs-be:
	docker compose logs -f backend

build:
	docker compose build --no-cache

clean:
	docker compose --profile https down -v --remove-orphans

# ── local dev ─────────────────────────────────────────────────────────────────
# Install backend deps + test deps in a venv, then run tests
.venv:
	python3 -m venv .venv
	.venv/bin/pip install -q --upgrade pip
	.venv/bin/pip install -q -r backend/requirements.txt
	.venv/bin/pip install -q -r tests/requirements.txt

test: .venv
	PYTHONPATH=backend .venv/bin/pytest tests/ -v

lint: .venv
	.venv/bin/pip install -q ruff
	.venv/bin/ruff check backend/

# ── env setup ─────────────────────────────────────────────────────────────────
.env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — edit before running 'make up'"; \
	fi

env: .env

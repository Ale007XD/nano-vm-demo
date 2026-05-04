"""
nano-vm demo backend
FastAPI (HTTP API for Mini App) + aiogram (Telegram bot polling) in one process.
"""

import asyncio
import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import NanoVMAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# ── AGENT (singleton) ──────────────────────────────────────────────────────────
agent = NanoVMAgent(demo_mode=DEMO_MODE)

# ── AIOGRAM ───────────────────────────────────────────────────────────────────
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "nano-vm demo bot\n\n"
        "Send me a reading request:\n"
        "  /tarot <name> | <dob> | <color> | <question>\n\n"
        "Example:\n"
        "  /tarot Anna | 12.05.1990 | blue | Is relocation right?\n\n"
        "Each response includes a full execution trace."
    )


@router.message(Command("tarot"))
async def cmd_tarot(message: Message) -> None:
    args = (message.text or "").removeprefix("/tarot").strip()
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 4:
        await message.answer(
            "Usage: /tarot <name> | <dob> | <color> | <question>\n"
            "Example: /tarot Anna | 12.05.1990 | blue | Is relocation right?"
        )
        return

    name, dob, color, question = parts[0], parts[1], parts[2], " | ".join(parts[3:])
    await message.answer("Running nano-vm program… ⏳")

    result = await agent.run_tarot(name=name, dob=dob, color=color, question=question)
    text = _format_trace(result)
    await message.answer(text, parse_mode="HTML")


def _format_trace(result: dict) -> str:
    lines = [
        f"<b>nano-vm trace</b>  run {result['run_id']}",
        "",
    ]
    for s in result["steps"]:
        icon = "◆" if s["type"] == "llm" else "✓"
        lines.append(f"<code>{icon} {s['id']:<18} {s['type']:<8} {s['duration_ms']}ms</code>")
        if s.get("detail"):
            lines.append(f"<code>  └ {s['detail']}</code>")

    lines += [
        "",
        f"<code>hash    {result['hash']}</code>",
        f"<code>total   {result['duration_ms']}ms</code>",
        "",
        f"<i>{result['output']}</i>",
    ]
    return "\n".join(lines)


# ── FASTAPI ───────────────────────────────────────────────────────────────────

class TarotRequest(BaseModel):
    name: str
    dob: str
    color: str = "blue"
    question: str
    run_id: Optional[str] = None


class RepeatRequest(BaseModel):
    run_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start bot polling in background if token provided
    if BOT_TOKEN:
        bot = Bot(token=BOT_TOKEN)
        dp = Dispatcher()
        dp.include_router(router)
        task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        log.info("Telegram bot polling started")
        yield
        task.cancel()
        await bot.session.close()
    else:
        log.warning("BOT_TOKEN not set — Telegram polling disabled")
        yield


app = FastAPI(title="nano-vm demo", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "demo_mode": DEMO_MODE}


@app.post("/api/tarot")
async def api_tarot(req: TarotRequest):
    result = await agent.run_tarot(
        name=req.name,
        dob=req.dob,
        color=req.color,
        question=req.question,
    )
    return result


@app.post("/api/repeat")
async def api_repeat(req: RepeatRequest):
    result = await agent.repeat_run(req.run_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="run_id not found")
    return result


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")

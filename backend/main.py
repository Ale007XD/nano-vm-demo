"""
nano-vm demo backend
FastAPI (HTTP API for Mini App/landing) + aiogram (Telegram bot polling).
Both run in the same process via asyncio.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import NanoVMAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# ── singleton agent ────────────────────────────────────────────────────────────
agent = NanoVMAgent(demo_mode=DEMO_MODE)


# ── aiogram bot ───────────────────────────────────────────────────────────────
def _build_dispatcher():
    from aiogram import Bot, Dispatcher, Router
    from aiogram.filters import Command
    from aiogram.types import Message

    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "nano-vm demo bot\n\n"
            "Send a reading request:\n"
            "  /tarot <name> | <dob> | <color> | <question>\n\n"
            "Example:\n"
            "  /tarot Anna | 12.05.1990 | blue | Is relocation right?\n\n"
            "Every response includes a full execution trace."
        )

    @router.message(Command("tarot"))
    async def cmd_tarot(message: Message) -> None:
        raw = (message.text or "").removeprefix("/tarot").strip()
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 4:
            await message.answer(
                "Usage: /tarot <name> | <dob> | <color> | <question>\n"
                "Example: /tarot Anna | 12.05.1990 | blue | Is relocation right?"
            )
            return

        name, dob, color = parts[0], parts[1], parts[2]
        question = " | ".join(parts[3:])
        await message.answer("Running nano-vm… ⏳")

        try:
            result = await agent.run_tarot(name=name, dob=dob, color=color, question=question)
        except Exception as exc:
            log.exception("run_tarot failed")
            await message.answer(f"Error: {exc}")
            return

        lines = [f"<b>nano-vm trace</b>  {result['run_id']}", ""]
        for s in result["steps"]:
            icon = "◆" if s["type"] == "llm" else "✓"
            lines.append(
                f"<code>{icon} {s['id']:<18} {s['type']:<8} {s['duration_ms']}ms</code>"
            )
            if s.get("detail"):
                lines.append(f"<code>  └ {s['detail']}</code>")
        lines += [
            "",
            f"<code>hash    {result['hash']}</code>",
            f"<code>total   {result['duration_ms']}ms</code>",
            "",
            f"<i>{result['output']}</i>",
        ]
        await message.answer("\n".join(lines), parse_mode="HTML")

    dp = Dispatcher()
    dp.include_router(router)
    return dp


# ── lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await agent.initialize()
    log.info("Agent initialized (demo_mode=%s)", DEMO_MODE)

    if BOT_TOKEN:
        from aiogram import Bot
        bot = Bot(token=BOT_TOKEN)
        dp = _build_dispatcher()
        task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        log.info("Telegram bot polling started")
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
    else:
        log.warning("BOT_TOKEN not set — Telegram polling disabled")
        yield


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(title="nano-vm demo", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ── schemas ───────────────────────────────────────────────────────────────────
class TarotRequest(BaseModel):
    name: str
    dob: str
    color: str = "blue"
    question: str


class RepeatRequest(BaseModel):
    run_id: str


# ── endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "demo_mode": DEMO_MODE}


@app.post("/api/tarot")
async def api_tarot(req: TarotRequest):
    try:
        return await agent.run_tarot(
            name=req.name,
            dob=req.dob,
            color=req.color,
            question=req.question,
        )
    except Exception as exc:
        log.exception("api_tarot error")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/repeat")
async def api_repeat(req: RepeatRequest):
    result = await agent.repeat_run(req.run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"run_id {req.run_id!r} not found")
    return result


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")

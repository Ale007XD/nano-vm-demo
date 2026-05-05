"""
NanoVMAgent — deterministic tarot program execution.

LLM cache: Redis (persistent across restarts) → in-memory fallback.
DEMO_MODE=true  → mock LLM, no API keys needed.
DEMO_MODE=false → real LLM via OpenAI-compatible or Anthropic.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Optional

from programs.tarot_profile import TAROT_PROGRAM  # noqa: F401 (reference)
from tools.seed import generate_seed
from tools.cards import tarot_draw
from tools.llm_interpret import llm_interpret
from tools.respond import respond_tool

log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")


class _Cache:
    """Two-level cache: Redis (persistent) → in-memory dict (fallback)."""

    def __init__(self) -> None:
        self._mem: dict[str, str] = {}
        self._redis = None

    async def connect(self) -> None:
        if not REDIS_URL:
            log.info("REDIS_URL not set — using in-memory LLM cache")
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await self._redis.ping()
            log.info("Redis LLM cache connected: %s", REDIS_URL)
        except Exception as exc:
            log.warning("Redis unavailable (%s) — falling back to in-memory cache", exc)
            self._redis = None

    async def get(self, key: str) -> Optional[str]:
        if self._redis:
            try:
                return await self._redis.get(f"llm:{key}")
            except Exception:
                pass
        return self._mem.get(key)

    async def set(self, key: str, value: str) -> None:
        self._mem[key] = value
        if self._redis:
            try:
                # TTL 7 days — LLM responses are deterministic, safe to cache long
                await self._redis.set(f"llm:{key}", value, ex=604800)
            except Exception:
                pass


class NanoVMAgent:
    def __init__(self, demo_mode: bool = True) -> None:
        self.demo_mode = demo_mode
        self._cache = _Cache()
        # run store: run_id → {result, params}
        self._runs: dict[str, dict] = {}

    async def initialize(self) -> None:
        await self._cache.connect()

    # ── PUBLIC ─────────────────────────────────────────────────────────────────

    async def run_tarot(
        self,
        name: str,
        dob: str,
        color: str,
        question: str,
    ) -> dict:
        run_id = self._make_run_id(name, dob, color, question)
        t_start = time.monotonic()
        steps: list[dict] = []

        # step 1 — generate_seed
        s1 = await self._run_tool(
            step_id="generate_seed",
            fn=generate_seed,
            kwargs={"name": name, "dob": dob, "color": color, "question": question},
        )
        steps.append(s1)
        seed: int = s1["_value"]

        # step 2 — draw_cards
        s2 = await self._run_tool(
            step_id="draw_cards",
            fn=tarot_draw,
            kwargs={"seed": seed},
        )
        steps.append(s2)
        cards: list[str] = s2["_value"]

        # step 3 — llm_interpret (cached)
        prompt = self._build_prompt(name, question, cards)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        cached_resp = await self._cache.get(prompt_hash)

        t_llm = time.monotonic()
        if cached_resp is not None:
            interpretation = cached_resp
            llm_ms = int((time.monotonic() - t_llm) * 1000) or 1
            llm_detail = "(cached) deterministic"
        else:
            interpretation = await llm_interpret(
                prompt=prompt,
                demo_mode=self.demo_mode,
                seed=seed,
            )
            await self._cache.set(prompt_hash, interpretation)
            llm_ms = int((time.monotonic() - t_llm) * 1000)
            llm_detail = "(live) cached for future runs"

        steps.append({
            "id": "llm_interpret",
            "type": "llm",
            "status": "ok",
            "duration_ms": max(llm_ms, 1),
            "detail": llm_detail,
        })

        # step 4 — respond
        s4 = await self._run_tool(
            step_id="respond",
            fn=respond_tool,
            kwargs={"text": interpretation},
        )
        steps.append(s4)

        total_ms = int((time.monotonic() - t_start) * 1000)
        run_hash = self._compute_hash(name, dob, color, question, cards, interpretation)

        result = {
            "run_id": run_id,
            "hash": run_hash,
            "duration_ms": total_ms,
            "steps": [self._clean_step(s) for s in steps],
            "output": interpretation,
            "diff": None,
        }
        self._runs[run_id] = {
            "result": result,
            "params": {"name": name, "dob": dob, "color": color, "question": question},
        }
        return result

    async def repeat_run(self, run_id: str) -> Optional[dict]:
        stored = self._runs.get(run_id)
        if stored is None:
            return None
        p = stored["params"]
        new_result = await self.run_tarot(**p)
        diff = self._diff(stored["result"], new_result)
        new_result["diff"] = diff
        return new_result

    # ── INTERNAL ───────────────────────────────────────────────────────────────

    async def _run_tool(self, step_id: str, fn, kwargs: dict) -> dict:
        t = time.monotonic()
        loop = asyncio.get_event_loop()
        value = await loop.run_in_executor(None, lambda: fn(**kwargs))
        ms = max(int((time.monotonic() - t) * 1000), 1)
        if isinstance(value, list):
            detail = ", ".join(str(v) for v in value)
        else:
            detail = str(value)[:80]
        return {
            "id": step_id,
            "type": "local",
            "status": "ok",
            "duration_ms": ms,
            "detail": detail,
            "_value": value,
        }

    @staticmethod
    def _clean_step(s: dict) -> dict:
        return {k: v for k, v in s.items() if not k.startswith("_")}

    @staticmethod
    def _make_run_id(name: str, dob: str, color: str, question: str) -> str:
        raw = "|".join([
            name.strip().lower(), dob.strip(),
            color.strip().lower(), question.strip().lower(),
        ])
        digest = hashlib.md5(raw.encode()).hexdigest()[:8].upper()
        return f"0x{digest}"

    @staticmethod
    def _compute_hash(
        name: str, dob: str, color: str, question: str,
        cards: list, interp: str,
    ) -> str:
        payload = "|".join([name, dob, color, question, ",".join(cards), interp[:32]])
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @staticmethod
    def _build_prompt(name: str, question: str, cards: list) -> str:
        return (
            f"You are a tarot reader. The querent is {name}. "
            f"Their question: {question}\n"
            f"Cards drawn: {', '.join(cards)}.\n"
            "Give a concise, meaningful interpretation in 2-3 sentences. "
            "Do not mention the card names explicitly — speak to the essence."
        )

    @staticmethod
    def _diff(ref: dict, new: dict) -> Optional[dict]:
        if ref["hash"] == new["hash"]:
            return None
        ref_steps = {s["id"]: s for s in ref["steps"]}
        diverged = [
            s["id"] for s in new["steps"]
            if ref_steps.get(s["id"], {}).get("detail") != s.get("detail")
        ]
        return {
            "ref_hash": ref["hash"],
            "new_hash": new["hash"],
            "diverged_steps": diverged,
            "reason": f"Steps diverged: {', '.join(diverged)}" if diverged else "Hash mismatch",
        }

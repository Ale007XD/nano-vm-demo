"""
NanoVMAgent — deterministic tarot program execution.

In DEMO_MODE=true: all tools are pure-Python stubs, LLM is mocked.
In DEMO_MODE=false: LLM step calls real provider (set OPENAI_API_KEY or ANTHROPIC_API_KEY).
"""

import asyncio
import hashlib
import os
import time
import uuid
from typing import Optional

from programs.tarot_profile import TAROT_PROGRAM
from tools.seed import generate_seed
from tools.cards import tarot_draw
from tools.llm_interpret import llm_interpret
from tools.respond import respond_tool


class NanoVMAgent:
    def __init__(self, demo_mode: bool = True) -> None:
        self.demo_mode = demo_mode
        # in-memory cache: run_id → result dict
        self._runs: dict[str, dict] = {}
        # LLM cache: prompt_hash → response str
        self._llm_cache: dict[str, str] = {}

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
        steps = []

        # step 1 — generate_seed (local tool)
        s1 = await self._run_tool(
            step_id="generate_seed",
            fn=generate_seed,
            kwargs={"name": name, "dob": dob, "color": color, "question": question},
        )
        steps.append(s1)
        seed: int = s1["_value"]

        # step 2 — draw_cards (local tool)
        s2 = await self._run_tool(
            step_id="draw_cards",
            fn=tarot_draw,
            kwargs={"seed": seed},
        )
        steps.append(s2)
        cards: list[str] = s2["_value"]

        # step 3 — llm_interpret (llm, cached)
        prompt = self._build_prompt(name, question, cards)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        cached = self._llm_cache.get(prompt_hash)

        s3_start = time.monotonic()
        if cached is not None:
            interpretation = cached
            llm_ms = 7
            llm_detail = "(cached) deterministic"
        else:
            interpretation = await llm_interpret(
                prompt=prompt,
                demo_mode=self.demo_mode,
                seed=seed,
            )
            self._llm_cache[prompt_hash] = interpretation
            llm_ms = int((time.monotonic() - s3_start) * 1000)
            llm_detail = "(live) cached for future runs"

        steps.append({
            "id": "llm_interpret",
            "type": "llm",
            "status": "ok",
            "duration_ms": llm_ms,
            "detail": llm_detail,
        })

        # step 4 — respond (local tool)
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
        ref = stored["result"]
        diff = self._diff(ref, new_result)
        new_result["diff"] = diff
        return new_result

    # ── INTERNAL ───────────────────────────────────────────────────────────────

    async def _run_tool(self, step_id: str, fn, kwargs: dict) -> dict:
        t = time.monotonic()
        value = await asyncio.get_event_loop().run_in_executor(None, lambda: fn(**kwargs))
        ms = int((time.monotonic() - t) * 1000)
        detail = str(value)[:80] if not isinstance(value, list) else ", ".join(value)
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
        raw = "|".join([name.strip().lower(), dob.strip(), color.strip().lower(), question.strip().lower()])
        digest = hashlib.md5(raw.encode()).hexdigest()[:8].upper()
        return f"0x{digest}"

    @staticmethod
    def _compute_hash(name: str, dob: str, color: str, question: str, cards: list, interp: str) -> str:
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
        diverged = []
        ref_steps = {s["id"]: s for s in ref["steps"]}
        for s in new["steps"]:
            ref_s = ref_steps.get(s["id"])
            if ref_s and ref_s.get("detail") != s.get("detail"):
                diverged.append(s["id"])
        return {
            "ref_hash": ref["hash"],
            "new_hash": new["hash"],
            "diverged_steps": diverged,
            "reason": f"Steps diverged: {', '.join(diverged)}" if diverged else "Hash mismatch",
        }

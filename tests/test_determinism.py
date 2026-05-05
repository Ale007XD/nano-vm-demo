"""
Smoke tests for nano-vm-demo deterministic properties.
Run: pytest tests/ -v
No network required — all tools are pure Python.
"""

import asyncio
import sys
import os

# make backend importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from tools.seed import generate_seed
from tools.cards import tarot_draw
from agent import NanoVMAgent


# ── seed ──────────────────────────────────────────────────────────────────────

def test_seed_deterministic():
    """Same inputs → same seed."""
    s1 = generate_seed("Anna", "12.05.1990", "blue", "Is relocation right?")
    s2 = generate_seed("Anna", "12.05.1990", "blue", "Is relocation right?")
    assert s1 == s2


def test_seed_changes_on_name():
    s1 = generate_seed("Anna", "12.05.1990", "blue", "Q?")
    s2 = generate_seed("Anna_", "12.05.1990", "blue", "Q?")
    assert s1 != s2


def test_seed_case_insensitive():
    s1 = generate_seed("Anna", "12.05.1990", "Blue", "Q?")
    s2 = generate_seed("anna", "12.05.1990", "blue", "Q?")
    assert s1 == s2


# ── cards ─────────────────────────────────────────────────────────────────────

def test_cards_deterministic():
    seed = generate_seed("Anna", "12.05.1990", "blue", "Q?")
    c1 = tarot_draw(seed)
    c2 = tarot_draw(seed)
    assert c1 == c2


def test_cards_count():
    seed = generate_seed("Anna", "12.05.1990", "blue", "Q?")
    cards = tarot_draw(seed)
    assert len(cards) == 3


def test_cards_no_duplicates():
    seed = generate_seed("Anna", "12.05.1990", "blue", "Q?")
    cards = tarot_draw(seed)
    assert len(cards) == len(set(cards))


def test_cards_change_on_different_seed():
    s1 = generate_seed("Anna", "12.05.1990", "blue", "Q?")
    s2 = generate_seed("Boris", "01.01.1985", "red", "Q?")
    assert tarot_draw(s1) != tarot_draw(s2)


# ── agent end-to-end ──────────────────────────────────────────────────────────

PARAMS = dict(name="Anna", dob="12.05.1990", color="blue", question="Is relocation right?")


@pytest.mark.asyncio
async def test_agent_hash_deterministic():
    """Two runs with same input → same hash."""
    ag = NanoVMAgent(demo_mode=True)
    await ag.initialize()
    r1 = await ag.run_tarot(**PARAMS)
    r2 = await ag.run_tarot(**PARAMS)
    assert r1["hash"] == r2["hash"]


@pytest.mark.asyncio
async def test_agent_hash_changes_on_input():
    """Different name → different hash."""
    ag = NanoVMAgent(demo_mode=True)
    await ag.initialize()
    r1 = await ag.run_tarot(**PARAMS)
    r2 = await ag.run_tarot(**{**PARAMS, "name": "Boris"})
    assert r1["hash"] != r2["hash"]


@pytest.mark.asyncio
async def test_agent_trace_has_four_steps():
    ag = NanoVMAgent(demo_mode=True)
    await ag.initialize()
    r = await ag.run_tarot(**PARAMS)
    assert len(r["steps"]) == 4
    ids = [s["id"] for s in r["steps"]]
    assert ids == ["generate_seed", "draw_cards", "llm_interpret", "respond"]


@pytest.mark.asyncio
async def test_agent_llm_cached_on_repeat():
    """Second run should hit LLM cache → detail contains 'cached'."""
    ag = NanoVMAgent(demo_mode=True)
    await ag.initialize()
    await ag.run_tarot(**PARAMS)          # prime cache
    r2 = await ag.run_tarot(**PARAMS)
    llm_step = next(s for s in r2["steps"] if s["id"] == "llm_interpret")
    assert "cached" in llm_step["detail"]


@pytest.mark.asyncio
async def test_agent_repeat_run_no_diff():
    """repeat_run with same params → diff is None."""
    ag = NanoVMAgent(demo_mode=True)
    await ag.initialize()
    r1 = await ag.run_tarot(**PARAMS)
    r2 = await ag.repeat_run(r1["run_id"])
    assert r2 is not None
    assert r2["diff"] is None


@pytest.mark.asyncio
async def test_agent_step_durations_positive():
    ag = NanoVMAgent(demo_mode=True)
    await ag.initialize()
    r = await ag.run_tarot(**PARAMS)
    for s in r["steps"]:
        assert s["duration_ms"] >= 1


@pytest.mark.asyncio
async def test_agent_repeat_unknown_run_id():
    ag = NanoVMAgent(demo_mode=True)
    await ag.initialize()
    result = await ag.repeat_run("0xDEADBEEF")
    assert result is None

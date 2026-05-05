"""
API integration tests using FastAPI TestClient.
Run: pytest tests/test_api.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

# patch env before import
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("BOT_TOKEN", "")

from main import app

client = TestClient(app)

PAYLOAD = {
    "name": "Anna",
    "dob": "12.05.1990",
    "color": "blue",
    "question": "Is relocation the right move?",
}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "demo_mode" in data


def test_tarot_response_shape():
    r = client.post("/api/tarot", json=PAYLOAD)
    assert r.status_code == 200
    data = r.json()
    assert "run_id" in data
    assert "hash" in data
    assert "duration_ms" in data
    assert "steps" in data
    assert "output" in data
    assert isinstance(data["steps"], list)
    assert len(data["steps"]) == 4


def test_tarot_deterministic():
    r1 = client.post("/api/tarot", json=PAYLOAD)
    r2 = client.post("/api/tarot", json=PAYLOAD)
    assert r1.json()["hash"] == r2.json()["hash"]
    assert r1.json()["output"] == r2.json()["output"]


def test_tarot_different_name_different_hash():
    r1 = client.post("/api/tarot", json=PAYLOAD)
    r2 = client.post("/api/tarot", json={**PAYLOAD, "name": "Boris"})
    assert r1.json()["hash"] != r2.json()["hash"]


def test_tarot_step_ids():
    r = client.post("/api/tarot", json=PAYLOAD)
    ids = [s["id"] for s in r.json()["steps"]]
    assert ids == ["generate_seed", "draw_cards", "llm_interpret", "respond"]


def test_repeat_match():
    r1 = client.post("/api/tarot", json=PAYLOAD)
    run_id = r1.json()["run_id"]
    r2 = client.post("/api/repeat", json={"run_id": run_id})
    assert r2.status_code == 200
    data = r2.json()
    assert data["hash"] == r1.json()["hash"]
    assert data["diff"] is None


def test_repeat_unknown_run_id():
    r = client.post("/api/repeat", json={"run_id": "0xDEADBEEF"})
    assert r.status_code == 404


def test_tarot_llm_step_cached_on_second_run():
    client.post("/api/tarot", json=PAYLOAD)   # prime
    r2 = client.post("/api/tarot", json=PAYLOAD)
    llm = next(s for s in r2.json()["steps"] if s["id"] == "llm_interpret")
    assert "cached" in llm["detail"]
    assert llm["duration_ms"] < 100           # cache hit is fast

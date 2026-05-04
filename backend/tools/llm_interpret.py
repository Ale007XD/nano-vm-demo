"""
llm_interpret — LLM step.

DEMO_MODE=true  → picks a deterministic mock response based on seed.
DEMO_MODE=false → calls real LLM (OpenAI-compatible or Anthropic).
                  Set OPENAI_API_KEY / OPENAI_BASE_URL or ANTHROPIC_API_KEY.
"""

import os

MOCK_RESPONSES = [
    "The cards reveal a transition long overdue — what appears uncertain is already in motion beneath the surface. Trust the current, not the shore.",
    "A crossing of paths is indicated. The energy you carry into the decision will shape the outcome more than external forces. Clarity precedes movement.",
    "The spread suggests a hidden strength the seeker has not yet acknowledged. What you call doubt, the cards read as discernment. Proceed with measured confidence.",
    "Two forces in equilibrium — action and stillness. The moment of choice is nearer than it appears. The foundation is solid; the fear is not.",
    "An ending that clears the way. The cards do not mourn; they point forward. What must be released will make room for what is genuinely yours.",
]


async def llm_interpret(prompt: str, demo_mode: bool = True, seed: int = 0) -> str:
    if demo_mode:
        return _mock_response(seed)

    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if openai_key:
        return await _call_openai(prompt, openai_key)
    elif anthropic_key:
        return await _call_anthropic(prompt, anthropic_key)
    else:
        # fallback to mock if no keys configured
        return _mock_response(seed)


def _mock_response(seed: int) -> str:
    idx = seed % len(MOCK_RESPONSES)
    return MOCK_RESPONSES[idx]


async def _call_openai(prompt: str, api_key: str) -> str:
    import httpx

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0,  # deterministic
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def _call_anthropic(prompt: str, api_key: str) -> str:
    import httpx

    model = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"].strip()

# Tarot profile program definition (used as reference / documentation)
# Actual execution is handled by agent.py which implements the same step graph.

TAROT_PROGRAM = {
    "name": "tarot_profile",
    "version": "1.0.0",
    "steps": [
        {
            "id": "generate_seed",
            "type": "tool",
            "tool": "generate_seed",
            "inputs": ["name", "dob", "color", "question"],
        },
        {
            "id": "draw_cards",
            "type": "tool",
            "tool": "tarot_draw",
            "inputs": ["$generate_seed.output"],
        },
        {
            "id": "llm_interpret",
            "type": "llm",
            "prompt_template": (
                "You are a tarot reader. The querent is {name}. "
                "Their question: {question}\n"
                "Cards drawn: {cards}.\n"
                "Give a concise, meaningful interpretation in 2-3 sentences."
            ),
            "cache": True,
        },
        {
            "id": "respond",
            "type": "tool",
            "tool": "respond",
            "inputs": ["$llm_interpret.output"],
        },
    ],
}

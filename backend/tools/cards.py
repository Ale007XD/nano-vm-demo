"""
tarot_draw — draws 3 cards deterministically from seed.
Uses a seeded LCG, no random module (which could be affected by global state).
"""

MAJOR_ARCANA = [
    "The Fool",
    "The Magician",
    "The High Priestess",
    "The Empress",
    "The Emperor",
    "The Hierophant",
    "The Lovers",
    "The Chariot",
    "Strength",
    "The Hermit",
    "Wheel of Fortune",
    "Justice",
    "The Hanged Man",
    "Death",
    "Temperance",
    "The Devil",
    "The Tower",
    "The Star",
    "The Moon",
    "The Sun",
    "Judgement",
    "The World",
]


def _lcg(seed: int):
    """Linear congruential generator — fully deterministic."""
    s = seed & 0xFFFFFFFF
    while True:
        s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
        yield s


def tarot_draw(seed: int, count: int = 3) -> list[str]:
    deck = list(MAJOR_ARCANA)
    rng = _lcg(seed)
    drawn = []
    for _ in range(count):
        idx = next(rng) % len(deck)
        drawn.append(deck.pop(idx))
    return drawn

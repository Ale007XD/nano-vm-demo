"""
generate_seed — deterministic seed from user profile fields.
Pure function, no side effects.
"""

import hashlib


def generate_seed(name: str, dob: str, color: str, question: str) -> int:
    raw = "|".join(
        [
            name.strip().lower(),
            dob.strip(),
            color.strip().lower(),
            question.strip().lower(),
        ]
    )
    digest = hashlib.sha256(raw.encode()).digest()
    # take first 4 bytes as unsigned int
    return int.from_bytes(digest[:4], "big")

"""Deterministic matching against the target junior remote developer profile."""

import re

PREFERRED_TECHNOLOGIES = (
    "python", "fastapi", "postgresql", "sqlalchemy", "docker", "aws", "git",
)
TITLE_PATTERN = re.compile(r"\b(?:backend|back[\s-]+end|python|software)\b", re.IGNORECASE)


def calculate_match_score(
    *, title: str, description: str, remote: bool, seniority: str
) -> int:
    text = f"{title}\n{description}"
    matches = sum(
        bool(re.search(rf"\b{technology}\b", text, re.IGNORECASE))
        for technology in PREFERRED_TECHNOLOGIES
    )
    score = round(60 * matches / len(PREFERRED_TECHNOLOGIES))
    if remote:
        score += 15
    if seniority.strip().casefold() == "junior":
        score += 15
    if TITLE_PATTERN.search(title):
        score += 10
    return max(0, min(100, score))

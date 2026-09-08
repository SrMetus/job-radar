"""Deterministic matching against the target junior remote developer profile."""

import re

from app.services.job_normalization import scoring_content

TECHNOLOGY_POINTS = {
    "python": 20, "fastapi": 10, "postgresql": 10,
    "sqlalchemy": 5, "docker": 5, "aws": 3, "git": 2,
}
SENIORITY_POINTS = {
    "junior": 20, "intern": 10, "unknown": 0,
    "senior": -15, "lead": -25, "staff": -25, "principal": -25,
}
TITLE_PATTERN = re.compile(
    r"\b(?:backend|back[\s-]+end|python|software\s+(?:engineer|developer)|developer|devops)\b",
    re.IGNORECASE,
)


def calculate_match_score(
    *, title: str, description: str, remote: bool, seniority: str
) -> int:
    title = scoring_content(title)
    text = f"{title}\n{scoring_content(description)}"
    matches = {
        technology for technology in TECHNOLOGY_POINTS
        if re.search(rf"\b{technology}\b", text, re.IGNORECASE)
    }
    relevant_title = bool(TITLE_PATTERN.search(title))
    if not relevant_title and not matches.intersection({"python", "fastapi", "sqlalchemy"}):
        return 0
    score = sum(TECHNOLOGY_POINTS[technology] for technology in matches)
    if remote:
        score += 10
    score += SENIORITY_POINTS.get(seniority.strip().casefold(), 0)
    if relevant_title:
        score += 15
    return max(0, min(100, score))

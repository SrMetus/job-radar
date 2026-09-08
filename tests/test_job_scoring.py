import pytest

from app.services.job_scoring import calculate_match_score


@pytest.mark.parametrize(
    "title, description, remote, seniority, expected",
    [
        ("Backend Python Developer", "FastAPI PostgreSQL SQLAlchemy Docker AWS Git", True, "junior", 100),
        ("Accountant", "Financial reporting", True, "senior", 15),
        ("Accountant", "Financial reporting", False, "senior", 0),
        ("BACKEND PYTHON DEVELOPER", "FASTAPI POSTGRESQL SQLALCHEMY DOCKER AWS GIT", True, " JuNiOr ", 100),
        ("", "", True, "", 15),
        ("", "", False, "junior", 15),
        ("", "Python FastAPI PostgreSQL", False, "", 26),
        ("Python Developer", "python PYTHON python", False, "", 19),
        ("Digital Marketing", "GitHub dockerized pythonesque awsomeness", False, "juniorish", 0),
        ("Back-end Developer", "", False, "", 10),
        ("Back end Developer", "", False, "", 10),
        ("Software Engineer", "", False, "", 10),
        ("Accountant", "backend software", False, "", 0),
        ("", "Python/FastAPI, PostgreSQL; SQLAlchemy (Docker) AWS Git.", False, "", 60),
        ("", "", False, "unknown", 0),
    ],
)
def test_score_rules(
    title: str, description: str, remote: bool, seniority: str, expected: int
) -> None:
    assert calculate_match_score(
        title=title, description=description, remote=remote, seniority=seniority
    ) == expected


@pytest.mark.parametrize("repetitions", [1, 10, 100])
def test_repetition_cannot_inflate_score(repetitions: int) -> None:
    score = calculate_match_score(
        title="Backend Python Software Developer",
        description="python fastapi postgresql sqlalchemy docker aws git " * repetitions,
        remote=True, seniority="junior",
    )
    assert score == 100
    assert 0 <= score <= 100

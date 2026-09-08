import pytest

from app.services.job_scoring import calculate_match_score


@pytest.mark.parametrize(
    "title, description, remote, seniority, expected",
    [
        ("Backend Python Developer", "FastAPI PostgreSQL SQLAlchemy Docker AWS Git", True, "junior", 100),
        ("Accountant", "Financial reporting", True, "senior", 0),
        ("Accountant", "Financial reporting", False, "senior", 0),
        ("BACKEND PYTHON DEVELOPER", "FASTAPI POSTGRESQL SQLALCHEMY DOCKER AWS GIT", True, " JuNiOr ", 100),
        ("Developer", "", True, "", 25),
        ("Developer", "", False, "junior", 35),
        ("", "Python FastAPI PostgreSQL", False, "", 40),
        ("Python Developer", "python PYTHON python", False, "", 35),
        ("Digital Marketing", "GitHub dockerized pythonesque awsomeness", False, "juniorish", 0),
        ("Back-end Developer", "", False, "", 15),
        ("Back end Developer", "", False, "", 15),
        ("Software Engineer", "", False, "", 15),
        ("Accountant", "backend software", False, "", 0),
        ("", "Python/FastAPI, PostgreSQL; SQLAlchemy (Docker) AWS Git.", False, "", 55),
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


@pytest.mark.parametrize("seniority, expected", [
    ("junior", 90), ("intern", 80), ("unknown", 70),
    ("senior", 55), ("lead", 45), ("staff", 45), ("principal", 45),
])
def test_seniority_ranking(seniority: str, expected: int) -> None:
    assert calculate_match_score(
        title="Python Backend Developer", description="FastAPI PostgreSQL Docker",
        remote=True, seniority=seniority,
    ) == expected


@pytest.mark.parametrize("title", [
    "Freelance Writer", "Sales Jedi", "Inside Sales Contractor", "Remote Office Assistant",
    "Software Sales", "Digital Marketing",
])
def test_unrelated_remote_roles(title: str) -> None:
    assert calculate_match_score(
        title=title, description="Uses AWS and Git", remote=True, seniority="junior"
    ) == 0


def test_unknown_python_role_is_moderate() -> None:
    assert calculate_match_score(
        title="Python Developer", description="", remote=True, seniority="unknown"
    ) == 45


def test_negative_score_is_clamped() -> None:
    assert calculate_match_score(
        title="Developer", description="", remote=False, seniority="principal"
    ) == 0


def test_metadata_does_not_inflate_eligible_role() -> None:
    assert calculate_match_score(
        title="Developer", description="Source: Python.org Job Board\nhttps://example.com/python/fastapi",
        remote=False, seniority="unknown",
    ) == 15

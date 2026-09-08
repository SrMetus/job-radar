from io import StringIO
from pathlib import Path
import runpy

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import config
from app.models import Job

ROOT = Path(__file__).resolve().parents[1]


def test_duplicate_url_rejected(engine: Engine, job_data: dict[str, str]) -> None:
    with Session(engine) as session:
        session.add(Job(**job_data))
        session.commit()
        session.add(Job(**job_data))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalar(text("SELECT count(*) FROM jobs")) == 1


@pytest.mark.parametrize("duplicates", [False, True])
def test_unique_migration_preserves_existing_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, duplicates: bool
) -> None:
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    configuration = Config(str(ROOT / "alembic.ini"))
    command.upgrade(configuration, "0001")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            for index in range(2):
                connection.execute(text(
                    "INSERT INTO jobs (title, company, location, seniority, description, url) "
                    "VALUES ('Title', 'Company', 'Location', 'junior', 'Description', :url)"
                ), {"url": f"https://example.com/{0 if duplicates else index}"})
            before = connection.execute(text("SELECT * FROM jobs ORDER BY id")).all()
        if duplicates:
            with pytest.raises(RuntimeError, match="duplicate URLs exist"):
                command.upgrade(configuration, "head")
        else:
            command.upgrade(configuration, "head")
            assert any(item["name"] == "uq_jobs_url" for item in inspect(engine).get_unique_constraints("jobs"))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT * FROM jobs ORDER BY id")).all() == before
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == ("0001" if duplicates else "0002")
        if not duplicates:
            command.downgrade(configuration, "0001")
            with engine.connect() as connection:
                assert connection.execute(text("SELECT * FROM jobs ORDER BY id")).all() == before
    finally:
        engine.dispose()


@pytest.mark.parametrize("value", [None, "", "   "])
def test_database_url_is_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str | None
) -> None:
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if value is not None:
        monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        config.get_database_url()


def test_environment_overrides_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=sqlite:///from_file.db\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert config.get_database_url() == "sqlite:///from_file.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    assert config.get_database_url() == "sqlite://"


def test_migration_persistence_and_downgrade(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    alembic_config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")

    # Execute session setup with an isolated test URL, without caching test globals.
    database = runpy.run_path(str(ROOT / "app/db/session.py"))
    engine = database["engine"]
    session_factory = database["SessionLocal"]
    try:
        with session_factory() as session:
            job = Job(
                title="Backend Developer", company="Example Company",
                location="Buenos Aires", seniority="junior",
                description="Build Python APIs.", url="https://example.com/jobs/1",
            )
            session.add(job)
            session.commit()
            job_id = job.id

        with session_factory() as session:
            saved = session.get(Job, job_id)
            assert saved is not None
            assert saved.title == "Backend Developer"
            assert saved.company == "Example Company"
            assert saved.location == "Buenos Aires"
            assert saved.seniority == "junior"
            assert saved.description == "Build Python APIs."
            assert saved.url == "https://example.com/jobs/1"
            assert saved.remote is False
            assert saved.created_at is not None

        with Session(engine) as session:
            session.add(Job(title="Missing required fields"))
            with pytest.raises(IntegrityError):
                session.commit()

        command.check(alembic_config)
        command.downgrade(alembic_config, "base")
        assert "jobs" not in inspect(engine).get_table_names()
        command.upgrade(alembic_config, "head")
        assert "jobs" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_postgresql_migration_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    # Offline rendering does not connect to PostgreSQL or require credentials.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/job_radar_test")
    output = StringIO()
    alembic_config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(alembic_config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE jobs" in sql
    assert "GENERATED ALWAYS AS IDENTITY" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "remote BOOLEAN DEFAULT false NOT NULL" in sql

    engine = create_engine(config.get_database_url())
    try:
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()

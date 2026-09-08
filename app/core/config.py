import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import HttpUrl, TypeAdapter, ValidationError

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def get_database_url() -> str:
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set before using the database.")
    return database_url


def get_external_job_source_url() -> str:
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    source_url = os.getenv("EXTERNAL_JOB_SOURCE_URL", "").strip()
    try:
        TypeAdapter(HttpUrl).validate_python(source_url)
    except ValidationError:
        raise ValueError("EXTERNAL_JOB_SOURCE_URL must be a valid HTTP(S) URL.") from None
    return source_url

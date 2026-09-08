import os
from pathlib import Path
from urllib.parse import urlsplit

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


def get_python_org_jobs_url() -> str:
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    url = os.getenv("PYTHON_ORG_JOBS_URL", "").strip()
    try:
        TypeAdapter(HttpUrl).validate_python(url)
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != "www.python.org"
                or parsed.path != "/jobs/" or parsed.username or parsed.password
                or parsed.port not in (None, 443)):
            raise ValueError
    except (ValidationError, ValueError):
        raise ValueError("PYTHON_ORG_JOBS_URL must point to https://www.python.org/jobs/.") from None
    return url

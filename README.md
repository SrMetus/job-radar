# Job Radar

A small FastAPI portfolio project with a health check endpoint.

## Setup

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
```

Activate the environment:

- Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

Install dependencies and start the development server:

```bash
python -m pip install -r requirements.txt
fastapi dev app/main.py
```

Visit <http://127.0.0.1:8000/health> for `{"status": "ok"}` or
<http://127.0.0.1:8000/docs> for API documentation.

## Database

Create a local PostgreSQL database, then copy `.env.example` to `.env` and replace
the connection placeholders with your own details. Use the
`postgresql+psycopg://` URL scheme and URL-encode special characters in credentials.
An existing `DATABASE_URL` environment variable takes precedence over `.env`.
Database operations fail clearly if the URL is missing; `/health` remains independent
of the database.

Apply the initial migration from the repository root:

```bash
python -m alembic upgrade head
```

For future model changes, generate and review a migration before applying it:

```bash
python -m alembic revision --autogenerate -m "describe change"
python -m alembic upgrade head
```

The `jobs` table stores the job title, company, location, remote flag, seniority,
description, and URL. These fields are required; `remote` defaults to false.
PostgreSQL generates the integer ID and timezone-aware creation timestamp.
Seniority is plain text until the API defines its allowed values.

## Tests

```bash
python -m pytest
```

Database tests use temporary SQLite databases for persistence, required fields,
and migration upgrade/downgrade checks. They also render PostgreSQL migration SQL
and verify the Psycopg driver loads. They do not require or connect to a live
PostgreSQL server, so they do not validate PostgreSQL runtime behavior.

## Structure

`app/main.py` contains the application and health endpoint. Database configuration
lives in `app/core/config.py`, Base and session setup in `app/db/`, and the typed
Job model in `app/models/`. Alembic migrations live in `alembic/versions/`.
The `schemas`, `api`, and `services` packages remain placeholders. Tests live in
`tests/`.

FastAPI's standard dependencies provide the development server and CLI. pytest
runs the tests, and HTTPX supports FastAPI's test client.
SQLAlchemy 2.x provides the ORM, Psycopg 3 (binary distribution) connects to
PostgreSQL without a local compiler, Alembic manages schema migrations, and
python-dotenv loads local database configuration.

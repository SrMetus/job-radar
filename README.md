# Job Radar

A small FastAPI portfolio project for storing and browsing job offers.

## Endpoints

- `GET /health`: API health check.
- `POST /jobs`: create a job and return it with status 201.
- `POST /jobs/import`: fetch the configured Remotive source and import new jobs.
- `GET /jobs`: list jobs by newest creation time first, then descending ID.
- `GET /jobs/{job_id}`: retrieve a job, or return 404 if it does not exist.

Apply migrations before using the jobs endpoints. Use <http://localhost:8000/docs>
to submit a job with `title`, `company`, `location`, `seniority`, `description`,
and `url` strings, plus an optional `remote` boolean (defaults to false).
Responses include the generated `id` and `created_at` timestamp.

`GET /jobs` accepts optional `remote=true|false`, `seniority` (case-insensitive
exact match), and `q` (case-insensitive substring search across title, company,
location, and description). Filters combine with AND; `q` matches any of its
four fields and treats `%` and `_` as literal characters. An empty `q` matches
all jobs. Pagination applies after filtering: `limit` defaults to 20 (allowed
range 1–100), and `offset` defaults to 0 (must be nonnegative). Invalid pagination
values return 422. Responses remain JSON lists.

Example: <http://localhost:8000/jobs?remote=true&seniority=junior&q=python&limit=10&offset=0>.

## External imports

Set `EXTERNAL_JOB_SOURCE_URL` in `.env` to the Remotive JSON endpoint shown in
`.env.example`. Existing shell environment values take precedence. For an
existing Docker stack, recreate the app after changing configuration:

```bash
docker compose up --build -d
curl -X POST http://localhost:8000/jobs/import
```

No request body or API key is needed. The response contains `fetched`, `created`,
and `skipped`; fetched counts the returned records, and skipped includes malformed
records and duplicate URLs. Missing/invalid source configuration returns 503.
Provider HTTP errors, timeouts, invalid JSON, and invalid response structure return
502 without importing anything. Valid records are committed together.

The importer supports Remotive's `jobs` JSON array only. It maps `company_name`
to company and `candidate_required_location` to location, sets remote to true and
seniority to `unknown`, and trims required text. Missing/blank/non-string fields
and invalid HTTP(S) job URLs are skipped. The description retains provider HTML
with a `Source: Remotive` attribution prefix; treat it as untrusted content if
displaying it in a future UI. `created_at` is the local import time, not the
provider publication date. No existing jobs are updated or removed.

Duplicate checks use exact, trimmed job URLs against the database and the current
batch. Repeating an import sequentially skips existing URLs. URL aliases and
tracking parameters are not canonicalized. There is no database uniqueness
constraint, preserving existing `POST /jobs` behavior and existing data; run
imports one at a time because concurrent imports can race.

Source: [Remotive public API](https://github.com/remotive-com/remote-jobs-api).
Its jobs are remote-only and delayed by 24 hours; location restrictions can still
apply. Remotive recommends at most four fetches per day and blocks excessive
requests. Preserve its attribution and links and follow its redistribution terms.
There is no automatic polling or retry loop. The example URL limits each fetch
to 20 software jobs; it is not a complete historical job archive.

## Docker setup

Install Docker with Compose (Docker Desktop with Linux containers on Windows).
From the repository root, copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux, use `cp .env.example .env`. Choose a local `POSTGRES_PASSWORD`
and set the same credentials in `DATABASE_URL`, URL-encoding special characters
in the URL. Keep the URL hostname as `db`, the Compose PostgreSQL service name.
`POSTGRES_DB` and `POSTGRES_USER` must also match the URL. For passwords containing
`$`, single-quote the value in `.env` to prevent Compose interpolation.
The `.env` file is ignored by Git and excluded from the image build.

Build and start the stack:

```bash
docker compose up --build
```

The app waits for PostgreSQL to be healthy and serves the API on
<http://localhost:8000/health>, returning `{"status": "ok"}`. API documentation is
at <http://localhost:8000/docs>. Add `-d` to run the stack in the background.
Port 8000 must be available. PostgreSQL is accessible to the app on `db:5432`
inside the Compose network.

In another terminal, apply the existing Alembic migrations and check the schema:

```bash
docker compose exec app python -m alembic upgrade head
docker compose exec app python -m alembic current
docker compose exec app python -m alembic check
```

Migrations run explicitly, not on every server startup. `/health` checks the API;
running Alembic verifies the app container can connect to PostgreSQL.

Run the tests inside the Python 3.12 app container:

```bash
docker compose exec app python -m pytest -p no:cacheprovider
```

Inspect status/logs or stop the stack:

```bash
docker compose ps
docker compose logs app db
docker compose down
```

PostgreSQL data persists in the named `postgres_data` volume across container
recreation and `docker compose down`. Database initialization variables only
apply to an empty volume; editing `.env` does not change existing database
credentials. Avoid `docker compose down -v` unless you intend to delete the data.

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

For development without Docker, create a local PostgreSQL database, then copy
`.env.example` to `.env` and replace the connection placeholders with your own
details, changing the URL hostname from `db` to `localhost`. Use the
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
Request/response schemas live in `app/schemas/`, and the jobs router and session
dependency live in `app/api/`. External fetching and Remotive normalization live
in `app/services/job_import.py`.
Tests live in `tests/`; API tests override the session dependency with isolated
SQLite databases.

FastAPI's standard dependencies provide the development server and CLI. pytest
runs the tests, and HTTPX handles external API requests and FastAPI's test client.
Automated import tests mock HTTP responses and never call the public provider.
SQLAlchemy 2.x provides the ORM, Psycopg 3 (binary distribution) connects to
PostgreSQL without a local compiler, Alembic manages schema migrations, and
python-dotenv loads local database configuration.

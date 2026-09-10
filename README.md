# Job Radar

A small FastAPI portfolio project for storing and browsing job offers.

## Endpoints

- `GET /health`: API health check.
- `POST /jobs`: create a job with status 201; an existing URL returns 409.
- `POST /jobs/import`: fetch the configured Remotive source and import new jobs.
- `POST /jobs/import/python-org`: import the public Python.org HTML listing.
- `GET /jobs`: list jobs by newest creation time first, then descending ID.
- `GET /jobs/{job_id}`: retrieve a job, or return 404 if it does not exist.

Apply migrations before using the jobs endpoints. Use <http://localhost:8000/docs>
to submit a job with `title`, `company`, `location`, `seniority`, `description`,
and `url` strings, plus an optional `remote` boolean (defaults to false).
Responses include the generated `id` and `created_at` timestamp.

Job responses also include a computed `match_score` from 0 to 100, targeting a
junior remote Python/backend developer. Technologies count once: Python 20,
FastAPI 10, PostgreSQL 10, SQLAlchemy 5, Docker 5, AWS 3, Git 2 (55 total).
A relevant development title adds 15, and remote adds 10. Normalized seniority
adds 20 for junior or 10 for intern; unknown adds zero. Senior subtracts 15;
lead, staff and principal subtract 25. The final score is clamped to 0–100.
Eligibility requires a backend/back-end/back end, Python, software engineer,
software developer, developer or DevOps title, or Python/FastAPI/SQLAlchemy in
actual content. Otherwise the score is zero, including unrelated remote roles.
Matching is case-insensitive with word boundaries. Source metadata, URLs and
HTML noise remain excluded. This is keyword relevance, not semantic analysis.
Scores are computed during response serialization and are not stored. Existing
listing filters and newest-first ordering are unchanged.

`GET /jobs` accepts optional `remote=true|false`, `seniority` (case-insensitive
exact match), and `q` (case-insensitive substring search across title, company,
location, and description). Filters combine with AND; `q` matches any of its
four fields and treats `%` and `_` as literal characters. An empty `q` matches
all jobs. Pagination applies after filtering: `limit` defaults to 20 (allowed
range 1–100), and `offset` defaults to 0 (must be nonnegative). Invalid pagination
values return 422. Responses remain JSON lists.

Example: <http://localhost:8000/jobs?remote=true&seniority=junior&q=python&limit=10&offset=0>.

Sorting accepts `sort=created_at|match_score` and `order=asc|desc`; defaults are
`created_at` and `desc`. Unsupported values return 422. Examples:

```text
GET /jobs?sort=match_score
GET /jobs?sort=match_score&order=asc
GET /jobs?remote=true&seniority=junior&sort=match_score
```

Date sorting uses SQL ordering and pagination (ID follows the date direction for
ties). Score sorting filters in SQL, loads all matching candidates, computes
scores in Python, sorts, then applies offset/limit. Equal scores always use
creation time descending, then ID descending, even for ascending scores. This
keeps pagination correct but uses memory and scoring time proportional to the
filtered candidate count; it is an intentional MVP trade-off. Scores are neither
stored nor duplicated in SQL.

## External imports

Both HTTP import endpoints require `X-Import-Secret` matching `IMPORT_SECRET`
in the server environment or `.env`. Choose a long random secret (for example,
generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
Never commit or log the secret; use HTTPS when deployed publicly. Missing or
incorrect headers return 403. An unset/blank server secret disables HTTP imports
with 503. Other endpoints remain unchanged. Swagger's Authorize button accepts
this header credential.

Set `EXTERNAL_JOB_SOURCE_URL` in `.env` to the Remotive JSON endpoint shown in
`.env.example`. Existing shell environment values take precedence. For an
existing Docker stack, recreate the app after changing configuration:

```bash
docker compose up --build -d
curl -X POST -H "X-Import-Secret: $IMPORT_SECRET" http://localhost:8000/jobs/import
```

The shell example assumes `IMPORT_SECRET` is exported in your shell; PowerShell
uses `$env:IMPORT_SECRET`. No request body or provider API key is needed.
The response contains `fetched`, `created`,
and `skipped`; fetched counts the returned records, and skipped includes malformed
records and duplicate URLs. Missing/invalid source configuration returns 503.
Provider HTTP errors, timeouts, invalid JSON, and invalid response structure return
502 without importing anything. Valid records are committed together.

The importer supports Remotive's `jobs` JSON array only. It maps `company_name`
to company and `candidate_required_location` to location, sets remote to true and
infers seniority from the title, and trims required text. Missing/blank/non-string
fields and invalid HTTP(S) job URLs are skipped. Descriptions become plain text
with paragraph/list line breaks; styles, scripts, images and source prefixes are
not added to job content. Records with no readable description are skipped.
`created_at` is the local import time, not the
provider publication date. No existing jobs are updated or removed.

Duplicate checks use exact, trimmed job URLs against the database and the current
batch. Repeating an import sequentially skips existing URLs. URL aliases and
tracking parameters are not canonicalized. The named database constraint
`uq_jobs_url` enforces URL uniqueness.
The pre-check avoids unnecessary inserts, while per-record savepoints recover
from competing URL inserts and count them as skipped. Other database failures
are re-raised and roll back the import. URL equality is exact and case-sensitive.

Migration `0002` preserves existing data. If duplicate URLs already exist, it
stops before adding the constraint; it never chooses or deletes a duplicate row.
Review conflicts with `SELECT url, count(*) FROM jobs GROUP BY url HAVING count(*) > 1`,
resolve them deliberately, and retry `alembic upgrade head`. PostgreSQL holds a
table lock during the check and constraint creation, so writes briefly wait.

Source: [Remotive public API](https://github.com/remotive-com/remote-jobs-api).
Its jobs are remote-only and delayed by 24 hours; location restrictions can still
apply. Remotive recommends at most four fetches per day and blocks excessive
requests. Preserve its attribution and links and follow its redistribution terms.
There is no automatic polling or retry loop. The example URL limits each fetch
to 20 software jobs; it is not a complete historical job archive.

## HTML imports

The HTML importer uses `PYTHON_ORG_JOBS_URL=https://www.python.org/jobs/` from
`.env`. Recreate the app after setting it, then call
`curl -X POST -H "X-Import-Secret: $IMPORT_SECRET" http://localhost:8000/jobs/import/python-org`.
It returns the same fetched/created/skipped summary as Remotive and shares its
URL pre-check, unique constraint, and savepoint conflict recovery.

Only the configured Python.org listing page is fetched, with no pagination or
detail-page crawling. Descriptions contain only available job categories, not
source names or URLs; they are empty when no categories are present.
Remote is inferred from title/location wording; missing evidence means false,
and seniority is inferred from the title. These heuristics can miss hybrid or ambiguous roles.
Malformed cards are skipped. Missing listing markup, HTTP errors, redirects,
and non-HTML responses return 502; invalid configuration returns 503. No bypass
of access restrictions is attempted. HTML selectors can break when the site
changes; imported rows are not refreshed or deleted when postings disappear.
Source: [Python.org Job Board](https://www.python.org/jobs/).
BeautifulSoup is the only added direct dependency; it uses Python's built-in
HTML parser. Automated tests use representative local HTML fixtures.

## External scheduling

The scheduler-friendly entry point runs once and exits:

```bash
python -m app.tasks.import_jobs
# With the Docker stack running:
docker compose exec -T app python -m app.tasks.import_jobs
```

Apply migrations first and configure `DATABASE_URL`, `EXTERNAL_JOB_SOURCE_URL`,
and `PYTHON_ORG_JOBS_URL`. The CLI accesses the database directly and does not
require `IMPORT_SECRET` or a running FastAPI server. It attempts Remotive and
Python.org sequentially, reporting missing/invalid source settings as failures.
Each source uses a fresh session that is closed after the attempt, rolling back
unfinished work. Successful sources commit independently through the existing
import services and retain their results if another source fails.

Output includes a line per source with status and fetched/created/skipped counts.
On failure the exception type is shown, with counts marked `unknown` because
the importer did not return a completed summary. Exit status is 0 when all
sources succeed and 1 if any fails, after all have been attempted. Database
initialization failure also exits 1. Repeated runs reuse URL deduplication.

Scheduling belongs outside FastAPI, for example in cron, systemd timers, or
Windows Task Scheduler. Configure the repository working directory, Python
environment, and database access there. Use a conservative interval (at most
four runs daily for Remotive), prevent overlapping runs in the scheduler, and
capture output and non-zero exit codes. There is no in-process scheduler,
background worker, polling loop, or automatic retry.

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

## Imported content normalization

Both importers infer seniority from whole-word title signals, case-insensitively.
Precedence for multiple signals is principal, staff, lead (including tech/team
lead), senior/sr, junior/jr/entry-level, then intern/internship. No signal means
unknown; absence of a senior keyword never implies junior.
Scoring ignores HTML markup, URLs and legacy Source: lines, while retaining real
visible job text. Provider attribution belongs outside the description; source
links remain in the job URL and this documentation.

Existing development rows are not automatically rewritten. Reimports skip their
URLs. To refresh them, back up the database, inspect the old imported rows by URL
and legacy Source: description prefix, and record their IDs. In a database
transaction, delete only those reviewed IDs, verify the affected count, and
commit (or roll back if unexpected). Then rebuild the Docker app and invoke the
corresponding import endpoint. Do not truncate the table or remove the volume
unless all development data is intentionally disposable. Reimported rows receive
new IDs and creation timestamps; postings no longer offered by the source will
not return. No startup cleanup or data migration is included.

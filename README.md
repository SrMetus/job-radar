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
No environment variables are required; `.env.example` is a placeholder.

## Tests

```bash
python -m pytest
```

## Structure

`app/main.py` contains the application and health endpoint. The `core`, `db`,
`models`, `schemas`, `api`, and `services` packages are empty placeholders for
future work. Tests live in `tests/`.

FastAPI's standard dependencies provide the development server and CLI. pytest
runs the tests, and HTTPX supports FastAPI's test client.

\# AGENTS.md



\## Project

Job Radar is a small portfolio project focused on backend development with Python and FastAPI.



\## Goal

Build a professional but intentionally small MVP that can be completed quickly and showcased on GitHub.



\## Stack

\- Python 3.12

\- FastAPI

\- PostgreSQL

\- SQLAlchemy

\- Alembic

\- Pydantic

\- pytest

\- Docker

\- Docker Compose

\- GitHub Actions



\## Development rules

\- Keep the architecture simple and production-oriented.

\- Prefer clear code over clever abstractions.

\- Do not over-engineer.

\- Use type hints.

\- Use environment variables for configuration.

\- Never hardcode secrets.

\- Add or update tests for implemented behavior.

\- Do not modify unrelated files.

\- Before making changes, inspect the repository and briefly explain the plan.

\- After making changes, run the relevant tests.

\- If a dependency is added, explain why it is needed.

\- Prefer small, incremental changes.



\## Architecture

Use this general structure:



app/

&#x20; main.py

&#x20; core/

&#x20; db/

&#x20; models/

&#x20; schemas/

&#x20; api/

&#x20; services/



tests/



\## MVP scope

The first version should support:

\- health check endpoint

\- create job offer

\- list job offers

\- get job offer by id

\- filter jobs by remote, seniority and technology

\- PostgreSQL persistence

\- Dockerized local development

\- basic tests



Do not add scraping, AI scoring, frontend, authentication, AWS or background jobs yet.


"""Run with python -m app.tasks.import_jobs."""

import sys

from app.services.import_runner import run_all_imports


def main() -> int:
    try:
        # Lazy initialization keeps importing this module free of DB side effects.
        from app.db.session import SessionLocal

        results = run_all_imports(SessionLocal)
    except Exception as error:
        print(f"Import command failed: {type(error).__name__}", file=sys.stderr)
        return 1

    for result in results:
        counts = " ".join(
            f"{field}={getattr(result, field) if getattr(result, field) is not None else 'unknown'}"
            for field in ("fetched", "created", "skipped")
        )
        status = f"FAILED ({result.error})" if result.failed else "OK"
        print(f"{result.source}: {status} {counts}")
    return int(any(result.failed for result in results))


if __name__ == "__main__":
    raise SystemExit(main())

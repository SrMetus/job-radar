from collections.abc import Generator
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.core.config import get_import_secret

import_secret_header = APIKeyHeader(name="X-Import-Secret", auto_error=False)


def require_import_secret(
    supplied: Annotated[str | None, Security(import_secret_header)],
) -> None:
    try:
        expected = get_import_secret()
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    if supplied is None or not compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid or missing import secret.")


def get_db() -> Generator[Session, None, None]:
    # Initialize database configuration only when a database endpoint is used.
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]

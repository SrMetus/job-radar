from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session


def get_db() -> Generator[Session, None, None]:
    # Initialize database configuration only when a database endpoint is used.
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]

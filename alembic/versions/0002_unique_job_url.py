"""Enforce unique job URLs without deleting or rewriting existing rows."""

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        # Hold the lock through constraint creation, including in offline SQL.
        op.execute("LOCK TABLE jobs IN ACCESS EXCLUSIVE MODE")
        op.execute("""
            DO $$ BEGIN
                IF EXISTS (SELECT url FROM jobs GROUP BY url HAVING count(*) > 1) THEN
                    RAISE EXCEPTION 'Cannot add uq_jobs_url: duplicate URLs exist. Review and resolve duplicates before retrying; no rows were changed.';
                END IF;
            END $$;
        """)
    else:
        duplicate = connection.execute(sa.text(
            "SELECT 1 FROM jobs GROUP BY url HAVING count(*) > 1 LIMIT 1"
        )).scalar()
        if duplicate is not None:
            raise RuntimeError(
                "Cannot add uq_jobs_url: duplicate URLs exist. Review and resolve "
                "duplicates before retrying; no rows were changed."
            )
    with op.batch_alter_table("jobs") as batch:
        batch.create_unique_constraint("uq_jobs_url", ["url"])


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("uq_jobs_url", type_="unique")

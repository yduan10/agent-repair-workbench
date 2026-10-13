"""P1-01a durable admission, global single slot and retained request tombstones."""

import sqlalchemy as sa
from alembic import op

revision = "0002_web_requests"
down_revision = "0001_run_store"


def upgrade() -> None:
    op.create_table(
        "web_requests",
        sa.Column("request_id", sa.String(), primary_key=True),
        sa.Column("payload_sha256", sa.String(), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Integer(), nullable=False),
        sa.CheckConstraint("active IN (0, 1)"),
        sa.CheckConstraint("cancel_requested IN (0, 1)"),
    )
    op.create_index(
        "ux_web_active", "web_requests", ["active"], unique=True, sqlite_where=sa.text("active = 1")
    )


def downgrade() -> None:
    if op.get_bind().exec_driver_sql("SELECT 1 FROM web_requests LIMIT 1").first():
        raise ValueError("migration_not_empty")
    op.drop_table("web_requests")

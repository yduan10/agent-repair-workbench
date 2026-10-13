"""Immutable initial P0-04 run-store schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001_run_store"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("profile", sa.String(), nullable=False),
        sa.Column("scenario", sa.String(), nullable=False),
        sa.Column("config_sha256", sa.String(), nullable=False),
        sa.Column("case_sha256", sa.String(), nullable=False),
        sa.Column("attempt_id", sa.String()),
        sa.Column("lease_until", sa.Float()),
        sa.Column("report_sha256", sa.String()),
        sa.Column("executor_state", sa.String()),
        sa.CheckConstraint("version >= 1"),
    )
    op.create_table(
        "attempts",
        sa.Column("attempt_id", sa.String(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.run_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("lease_token", sa.String(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float()),
        sa.Column("status", sa.String(), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column(
            "run_id", sa.String(), sa.ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("request_sha256", sa.String(), nullable=False),
        sa.UniqueConstraint("run_id", "version"),
    )
    op.create_table(
        "artifacts",
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.run_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "attempt_id",
            sa.String(),
            sa.ForeignKey("attempts.attempt_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("size >= 0 AND size <= 1048576"),
    )
    op.create_index("ix_runs_status_lease", "runs", ["status", "lease_until"])
    op.create_index("ix_runs_updated", "runs", ["updated_at"])


def downgrade() -> None:
    # All tables are checked inside the same exclusive writer transaction.
    for table in ("runs", "attempts", "events", "artifacts"):
        if op.get_bind().exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").first():
            raise ValueError("migration_not_empty")
    for table in ("artifacts", "events", "attempts", "runs"):
        op.drop_table(table)

"""Four durable identities per comparison; old repair ledger remains byte-for-byte intact."""

import sqlalchemy as sa
from alembic import op

revision = "0005_comparisons"
down_revision = "0004_repairs"


def upgrade() -> None:
    op.create_table(
        "repair_comparisons",
        sa.Column("comparison_id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("repair_tasks.task_id"), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column(
            "candidate_id",
            sa.String(),
            sa.ForeignKey("repair_candidates.candidate_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.UniqueConstraint("task_id", "request_id"),
        sa.CheckConstraint("length(payload) <= 32768"),
    )
    op.create_table(
        "repair_comparison_attempts",
        sa.Column("attempt_id", sa.String(), primary_key=True),
        sa.Column(
            "comparison_id",
            sa.String(),
            sa.ForeignKey("repair_comparisons.comparison_id"),
            nullable=False,
        ),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("report_sha256", sa.String()),
        sa.UniqueConstraint("comparison_id", "slot_index"),
        sa.CheckConstraint("slot_index >= 0 AND slot_index <= 3"),
        sa.CheckConstraint("status IN ('admitted','reported','unknown')"),
    )


def downgrade() -> None:
    for name in ("repair_comparisons", "repair_comparison_attempts"):
        if op.get_bind().exec_driver_sql(f"SELECT 1 FROM {name} LIMIT 1").first():
            raise ValueError("migration_not_empty")
    op.drop_table("repair_comparison_attempts")
    op.drop_table("repair_comparisons")

"""Independent repair tasks, bounded requests, candidate claims and event history."""

import sqlalchemy as sa
from alembic import op

revision = "0004_repairs"
down_revision = "0003_analyses"


def upgrade() -> None:
    op.create_table(
        "repair_tasks",
        sa.Column("task_id", sa.String(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.CheckConstraint("revision >= 0 AND revision < 256"),
        sa.CheckConstraint("length(payload) <= 32768"),
    )
    for name, identity in (("repair_requests", "request_id"), ("repair_events", "revision")):
        op.create_table(
            name,
            sa.Column(
                "task_id", sa.String(), sa.ForeignKey("repair_tasks.task_id"), primary_key=True
            ),
            (
                sa.Column("revision", sa.Integer(), primary_key=True)
                if identity == "revision"
                else sa.Column("request_id", sa.String(), primary_key=True)
            ),
            sa.Column("payload", sa.LargeBinary(), nullable=False),
            sa.Column("sha256", sa.String(), nullable=False),
            sa.CheckConstraint("length(payload) <= 32768"),
        )
    op.create_table(
        "repair_candidates",
        sa.Column("candidate_id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("repair_tasks.task_id"), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.UniqueConstraint("task_id", "request_id"),
        sa.UniqueConstraint("task_id", "sequence"),
        sa.CheckConstraint("sequence >= 1 AND sequence <= 2"),
        sa.CheckConstraint("length(payload) <= 32768"),
    )


def downgrade() -> None:
    for name in ("repair_tasks", "repair_requests", "repair_candidates", "repair_events"):
        if op.get_bind().exec_driver_sql(f"SELECT 1 FROM {name} LIMIT 1").first():
            raise ValueError("migration_not_empty")
    for name in ("repair_events", "repair_candidates", "repair_requests", "repair_tasks"):
        op.drop_table(name)

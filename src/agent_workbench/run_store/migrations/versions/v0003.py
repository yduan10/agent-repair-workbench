"""Independent safe analysis summaries, event ledger and bound executions."""

import sqlalchemy as sa
from alembic import op

revision = "0003_analyses"
down_revision = "0002_web_requests"


def upgrade() -> None:
    op.create_table(
        "analysis_summaries",
        sa.Column("task_id", sa.String(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.CheckConstraint("revision >= 0 AND revision < 256"),
        sa.CheckConstraint("length(summary_json) <= 262144"),
    )
    op.create_table(
        "analysis_events",
        sa.Column(
            "task_id", sa.String(), sa.ForeignKey("analysis_summaries.task_id"), primary_key=True
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("event_json", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.CheckConstraint("length(event_json) <= 16384"),
        sa.CheckConstraint("revision >= 0 AND revision < 256"),
    )
    op.create_table(
        "analysis_execution_links",
        sa.Column("record_id", sa.String(), sa.ForeignKey("runs.run_id"), primary_key=True),
        sa.Column(
            "task_id", sa.String(), sa.ForeignKey("analysis_summaries.task_id"), nullable=False
        ),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("payload_sha256", sa.String(), nullable=False),
        sa.UniqueConstraint("task_id", "request_id"),
    )


def downgrade() -> None:
    for table in ("analysis_summaries", "analysis_events", "analysis_execution_links"):
        if op.get_bind().exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").first():
            raise ValueError("migration_not_empty")
    for table in ("analysis_execution_links", "analysis_events", "analysis_summaries"):
        op.drop_table(table)

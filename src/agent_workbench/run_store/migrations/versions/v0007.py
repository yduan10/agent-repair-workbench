"""P1-01b once-only web analysis admission and durable cancellation."""

import sqlalchemy as sa
from alembic import op

revision = "0007_web_analyses"
down_revision = "0006_reproductions"
INDEX_SQL = (
    "CREATE UNIQUE INDEX ux_web_analysis_active ON web_analysis_requests (active) WHERE active = 1"
)


def upgrade() -> None:
    op.create_table(
        "web_analysis_requests",
        sa.Column("request_id", sa.String(), primary_key=True),
        sa.Column("payload_sha256", sa.String(), nullable=False),
        sa.Column("case_name", sa.String(), nullable=False),
        sa.Column("intent", sa.String(), nullable=False),
        sa.Column("policy_sha256", sa.String(), nullable=False),
        sa.Column("initial_sha256", sa.String(), nullable=False),
        sa.Column("claim_sha256", sa.String(), nullable=False),
        sa.Column("consumed", sa.Integer(), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Integer(), nullable=False),
        sa.CheckConstraint("case_name IN ('output_mismatch','passing')"),
        sa.CheckConstraint("intent IN ('check_only','diagnose','propose_repair')"),
        sa.CheckConstraint("consumed IN (0, 1)"),
        sa.CheckConstraint("active IN (0, 1)"),
        sa.CheckConstraint("cancel_requested IN (0, 1)"),
    )
    op.execute(INDEX_SQL)


def downgrade() -> None:
    if op.get_bind().exec_driver_sql("SELECT 1 FROM web_analysis_requests LIMIT 1").first():
        raise ValueError("migration_not_empty")
    op.drop_table("web_analysis_requests")

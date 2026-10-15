"""P1-01 B1a once-only web repair admission and durable cancellation."""

import sqlalchemy as sa
from alembic import op

revision = "0008_web_repairs"
down_revision = "0007_web_analyses"
INDEX_SQL = (
    "CREATE UNIQUE INDEX ux_web_repair_active ON web_repair_requests (active) WHERE active = 1"
)


# SQLite guards complement the transactional capability check. In particular,
# consumed=1 -> 0 must not resurrect a claim while task revision is still zero.
TRIGGERS = {
    "web_repair_immutable": """CREATE TRIGGER web_repair_immutable
BEFORE UPDATE ON web_repair_requests
WHEN NEW.request_id IS NOT OLD.request_id
OR NEW.payload_sha256 IS NOT OLD.payload_sha256
OR NEW.case_id IS NOT OLD.case_id OR NEW.mode IS NOT OLD.mode
OR NEW.policy_sha256 IS NOT OLD.policy_sha256
OR NEW.initial_sha256 IS NOT OLD.initial_sha256
OR NEW.claim_sha256 IS NOT OLD.claim_sha256
BEGIN SELECT RAISE(ABORT, 'web_repair_immutable'); END""",
    "web_repair_monotonic": """CREATE TRIGGER web_repair_monotonic
BEFORE UPDATE ON web_repair_requests
WHEN NEW.consumed < OLD.consumed OR NEW.cancel_requested < OLD.cancel_requested
OR NEW.active > OLD.active
BEGIN SELECT RAISE(ABORT, 'web_repair_monotonic'); END""",
    "web_repair_tombstone": """CREATE TRIGGER web_repair_tombstone
BEFORE DELETE ON web_repair_requests
BEGIN SELECT RAISE(ABORT, 'web_repair_tombstone'); END""",
}


def upgrade() -> None:
    op.create_table(
        "web_repair_requests",
        sa.Column("request_id", sa.String(), primary_key=True),
        sa.Column("payload_sha256", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("policy_sha256", sa.String(), nullable=False),
        sa.Column("initial_sha256", sa.String(), nullable=False),
        sa.Column("claim_sha256", sa.String(), nullable=False),
        sa.Column("consumed", sa.Integer(), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Integer(), nullable=False),
        sa.CheckConstraint("case_id IN ('output_mismatch','counter_offset')"),
        sa.CheckConstraint("mode IN ('single_role','three_role')"),
        sa.CheckConstraint("consumed IN (0, 1)"),
        sa.CheckConstraint("active IN (0, 1)"),
        sa.CheckConstraint("cancel_requested IN (0, 1)"),
    )
    op.execute(INDEX_SQL)
    for statement in TRIGGERS.values():
        op.execute(statement)


def downgrade() -> None:
    if op.get_bind().exec_driver_sql("SELECT 1 FROM web_repair_requests LIMIT 1").first():
        raise ValueError("migration_not_empty")
    op.drop_table("web_repair_requests")

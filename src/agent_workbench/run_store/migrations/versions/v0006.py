"""T05 reservation and shared T05/T07 identity ownership, with no old ledger rewriting."""

import sqlalchemy as sa
from alembic import op

revision = "0006_reproductions"
down_revision = "0005_comparisons"

# Fixed SQL is also checked by the store before writes: missing guards fail closed.
TRIGGERS = {
    "repair_comparison_identity": """CREATE TRIGGER repair_comparison_identity
AFTER INSERT ON repair_comparison_attempts BEGIN
INSERT INTO repair_execution_identities(attempt_id, kind, owner_id)
VALUES (NEW.attempt_id, 'comparison', NEW.comparison_id); END""",
    "repair_reproduction_identity": """CREATE TRIGGER repair_reproduction_identity
AFTER INSERT ON repair_reproductions BEGIN
INSERT INTO repair_execution_identities(attempt_id, kind, owner_id)
VALUES (NEW.attempt_id, 'reproduction', NEW.task_id || ':' || NEW.request_id); END""",
}


def upgrade() -> None:
    op.create_table(
        "repair_execution_identities",
        sa.Column("attempt_id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.CheckConstraint("kind IN ('comparison','reproduction')"),
    )
    op.create_table(
        "repair_reproductions",
        sa.Column("task_id", sa.String(), sa.ForeignKey("repair_tasks.task_id"), primary_key=True),
        sa.Column("request_id", sa.String(), primary_key=True),
        sa.Column("attempt_id", sa.String(), nullable=False, unique=True),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.CheckConstraint("length(payload) <= 32768"),
    )
    op.execute("""INSERT INTO repair_execution_identities(attempt_id,kind,owner_id)
SELECT attempt_id,'comparison',comparison_id FROM repair_comparison_attempts""")
    for statement in TRIGGERS.values():
        op.execute(statement)


def downgrade() -> None:
    if op.get_bind().exec_driver_sql("SELECT 1 FROM repair_reproductions LIMIT 1").first():
        raise ValueError("migration_not_empty")
    for name in TRIGGERS:
        op.execute(f"DROP TRIGGER {name}")
    op.drop_table("repair_reproductions")
    op.drop_table("repair_execution_identities")

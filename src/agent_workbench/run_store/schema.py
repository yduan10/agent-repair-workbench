"""SQLAlchemy Core schema; runtime queries never expose private attempt rows."""

from sqlalchemy import Column, Float, ForeignKey, Integer, LargeBinary, MetaData, String, Table

metadata = MetaData()
runs = Table(
    "runs",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("status", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Column("profile", String, nullable=False),
    Column("scenario", String, nullable=False),
    Column("config_sha256", String, nullable=False),
    Column("case_sha256", String, nullable=False),
    Column("attempt_id", String),
    Column("lease_until", Float),
    Column("report_sha256", String),
    Column("executor_state", String),
)
attempts = Table(
    "attempts",
    metadata,
    Column("attempt_id", String, primary_key=True),
    Column("run_id", ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("lease_token", String, nullable=False),
    Column("started_at", Float, nullable=False),
    Column("finished_at", Float),
    Column("status", String, nullable=False),
)
events = Table(
    "events",
    metadata,
    Column("event_id", String, primary_key=True),
    Column("run_id", ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("kind", String, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("request_sha256", String, nullable=False),
)
artifacts = Table(
    "artifacts",
    metadata,
    Column("run_id", ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True),
    Column("attempt_id", ForeignKey("attempts.attempt_id", ondelete="CASCADE"), nullable=False),
    Column("sha256", String, nullable=False),
    Column("size", Integer, nullable=False),
    Column("payload", LargeBinary, nullable=False),
)

# Deliberately no FK: deduplication tombstones survive run pruning.
web_requests = Table(
    "web_requests",
    metadata,
    Column("request_id", String, primary_key=True),
    Column("payload_sha256", String, nullable=False),
    Column("active", Integer, nullable=False),
    Column("cancel_requested", Integer, nullable=False),
)

"""Atomic admission and cancellation; retained IDs never become new executions."""

from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from agent_workbench.run_store.models import Claim, RunView, StoreError
from agent_workbench.run_store.schema import events, runs, web_requests
from agent_workbench.run_store.store import TERMINAL, RunStore, _uuid
from agent_workbench.web_runs.fencing import OwnerFence
from agent_workbench.web_runs.models import ReproductionRequest


class WebRunStore(RunStore):
    def _existing(self, connection: Connection, request: ReproductionRequest) -> RunView | None:
        row = (
            connection.execute(
                select(web_requests).where(web_requests.c.request_id == request.request_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        if row["payload_sha256"] != request.fingerprints()[2]:
            raise StoreError("request_conflict")
        if (
            connection.execute(
                select(runs.c.run_id).where(runs.c.run_id == request.request_id)
            ).first()
            is None
        ):
            raise StoreError("request_gone")
        return self._view(connection, request.request_id)

    def existing(self, request: ReproductionRequest) -> RunView | None:
        with self._transaction() as connection:
            return self._existing(connection, request)

    def active_id(self) -> str | None:
        with self._transaction() as connection:
            return connection.execute(
                select(web_requests.c.request_id).where(web_requests.c.active == 1)
            ).scalar_one_or_none()

    def is_active(self, run_id: str) -> bool:
        _uuid(run_id)
        return self.active_id() == run_id

    def _release_safe(self, connection: Connection) -> bool:
        active = connection.execute(
            select(web_requests.c.request_id).where(web_requests.c.active == 1)
        ).scalar_one_or_none()
        if active is None:
            return True
        run = self._view(connection, active)
        if run.status not in TERMINAL:
            return False
        latest = connection.execute(
            select(events.c.kind)
            .where(events.c.run_id == active)
            .order_by(events.c.version.desc())
            .limit(1)
        ).scalar()
        safe = latest == "reconciled" and run.executor_state in ("absent", "stopped")
        if latest == "finished" and run.executor_state == "absent":
            report = self._report(connection, run)
            safe = report.execution.cleanup in ("removed", "not_created") and (
                report.execution.error
                not in ("cleanup_unconfirmed", "create_unconfirmed", "attach_cleanup_unconfirmed")
            )
        if safe:
            connection.execute(
                update(web_requests).where(web_requests.c.request_id == active).values(active=0)
            )
        return safe

    def release_safe(self, fence: OwnerFence) -> bool:
        fence.require(self.directory)
        with self._transaction(write=True) as connection:
            return self._release_safe(connection)

    def admit(self, request: ReproductionRequest, fence: OwnerFence) -> Claim | RunView:
        fence.require(self.directory)
        config_hash, case_hash, payload_hash = request.fingerprints()
        with self._transaction(write=True) as connection:
            existing = self._existing(connection, request)
            if existing is not None:
                return existing
            if (
                connection.execute(
                    select(runs.c.run_id).where(runs.c.run_id == request.request_id)
                ).first()
                is not None
            ):
                raise StoreError("request_conflict")
            if not self._release_safe(connection):
                raise StoreError("runner_busy")
            run = self._create(
                connection,
                request.request_id,
                "isolated-fixture",
                request.scenario,
                config_hash,
                case_hash,
            )
            claim = self._claim(connection, run.run_id, run.version)
            connection.execute(
                web_requests.insert().values(
                    request_id=request.request_id,
                    payload_sha256=payload_hash,
                    active=1,
                    cancel_requested=0,
                )
            )
            return claim

    def request_cancel(self, run_id: str) -> bool:
        """True means cancellation requested; False means already finished."""
        _uuid(run_id)
        with self._transaction(write=True) as connection:
            row = (
                connection.execute(select(web_requests).where(web_requests.c.request_id == run_id))
                .mappings()
                .first()
            )
            if row is None:
                raise StoreError("web_run_not_found")
            run = connection.execute(select(runs.c.status).where(runs.c.run_id == run_id)).first()
            if not row["active"] or run is None or run[0] in TERMINAL:
                return False
            connection.execute(
                update(web_requests)
                .where(web_requests.c.request_id == run_id)
                .values(cancel_requested=1)
            )
            return True

    def cancellation_requested(self, run_id: str) -> bool:
        _uuid(run_id)
        with self._transaction() as connection:
            value = connection.execute(
                select(web_requests.c.cancel_requested).where(web_requests.c.request_id == run_id)
            ).scalar_one_or_none()
            if value is None:
                raise StoreError("web_run_not_found")
            return bool(value)

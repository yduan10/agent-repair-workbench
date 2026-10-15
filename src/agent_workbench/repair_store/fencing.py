"""A task-specific POSIX owner fence; recovery never races a live owner."""

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.store import _uuid

try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX-only runtime
    fcntl = None  # type: ignore[assignment]


class RepairFence:
    def __init__(self, directory: Path, task_id: str) -> None:
        self.directory = directory.absolute()
        self.task_id = _uuid(task_id)
        self._mutex = RLock()
        self._guard_depth = 0
        self._fd: int | None = None
        self._pid: int | None = None

    def acquire(self) -> None:
        with self._mutex:
            self._acquire()

    def _acquire(self) -> None:
        if fcntl is None:
            raise StoreError("locking_unavailable")
        if self._fd is not None:
            raise StoreError("owner_already_locked")
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise StoreError("store_unavailable")
        fd: int | None = None
        try:
            fd = os.open(
                self.directory / f"repair-{self.task_id}.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise StoreError("locking_unavailable")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd = fd
            self._pid = os.getpid()
        except BlockingIOError:
            raise StoreError("repair_busy") from None
        except OSError:
            raise StoreError("locking_unavailable") from None
        finally:
            if fd is not None and fd != self._fd:
                os.close(fd)

    def require(self, directory: Path, task_id: str) -> None:
        if (
            self._fd is None
            or self._pid != os.getpid()
            or directory.absolute() != self.directory
            or task_id != self.task_id
        ):
            raise StoreError("owner_lock_required")

    @contextmanager
    def guard(self, directory: Path, task_id: str) -> Iterator[None]:
        # Reject fork-inherited ownership before touching an inherited mutex.
        self.require(directory, task_id)
        with self._mutex:
            self.require(directory, task_id)
            self._guard_depth += 1
            try:
                yield
                self.require(directory, task_id)
            finally:
                self._guard_depth -= 1

    def close(self) -> None:
        if self._pid is not None and self._pid != os.getpid():
            self._close()
            return
        with self._mutex:
            if self._guard_depth:
                raise StoreError("owner_lock_required")
            self._close()

    def _close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            self._pid = None

    def __enter__(self) -> "RepairFence":
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

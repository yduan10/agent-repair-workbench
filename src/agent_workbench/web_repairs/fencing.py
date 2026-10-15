"""One live browser repair owner per state directory, bound to acquisition and PID."""

import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from agent_workbench.run_store.models import StoreError

try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX-only runtime
    fcntl = None  # type: ignore[assignment]


class RepairWebFence:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.absolute()
        self._mutex = RLock()
        self._guard_depth = 0
        self._fd: int | None = None
        self._pid: int | None = None
        self._nonce: str | None = None

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
                self.directory / "repair-web-owner.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise StoreError("locking_unavailable")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            nonce = secrets.token_hex(32)
            self._fd, self._pid, self._nonce = fd, os.getpid(), nonce
        except BlockingIOError:
            raise StoreError("repair_busy") from None
        except OSError:
            raise StoreError("locking_unavailable") from None
        finally:
            if fd is not None and fd != self._fd:
                os.close(fd)

    def require(self, directory: Path, nonce: str | None = None) -> str:
        if (
            self._fd is None
            or self._pid != os.getpid()
            or self._nonce is None
            or directory.absolute() != self.directory
            or (nonce is not None and nonce != self._nonce)
        ):
            raise StoreError("owner_lock_required")
        try:
            held = os.fstat(self._fd)
            current = (self.directory / "repair-web-owner.lock").lstat()
            if not stat.S_ISREG(current.st_mode) or (held.st_dev, held.st_ino) != (
                current.st_dev,
                current.st_ino,
            ):
                raise StoreError("owner_lock_required")
        except OSError:
            raise StoreError("owner_lock_required") from None
        return self._nonce

    @contextmanager
    def guard(self, directory: Path, nonce: str | None = None) -> Iterator[None]:
        # Reject fork-inherited ownership before touching an inherited mutex.
        self.require(directory, nonce)
        with self._mutex:
            self.require(directory, nonce)
            self._guard_depth += 1
            try:
                yield
                self.require(directory, nonce)
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
            self._fd, self._pid, self._nonce = None, None, None

    def __enter__(self) -> "RepairWebFence":
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

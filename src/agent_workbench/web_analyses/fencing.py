"""P1-01b single browser analysis owner, independent of reproduction slots."""

import os
import stat
from pathlib import Path

from agent_workbench.run_store.models import StoreError

try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX-only runtime
    fcntl = None  # type: ignore[assignment]


class AnalysisWebFence:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.absolute()
        self._fd: int | None = None

    def acquire(self) -> None:
        if fcntl is None:
            raise StoreError("locking_unavailable")
        if self._fd is not None:
            raise StoreError("owner_already_locked")
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise StoreError("store_unavailable")
        fd: int | None = None
        try:
            fd = os.open(
                self.directory / "analysis-web-owner.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise StoreError("locking_unavailable")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd = fd
        except BlockingIOError:
            raise StoreError("analysis_busy") from None
        except OSError:
            raise StoreError("locking_unavailable") from None
        finally:
            if fd is not None and fd != self._fd:
                os.close(fd)

    def require(self, directory: Path) -> None:
        if self._fd is None or directory.absolute() != self.directory:
            raise StoreError("owner_lock_required")

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "AnalysisWebFence":
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

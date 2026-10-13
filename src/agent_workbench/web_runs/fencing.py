"""Cross-process owner fence: held through dispatch, execution, cleanup and commit."""

import os
import stat
from pathlib import Path

from agent_workbench.run_store.models import StoreError

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX explicitly unsupported
    fcntl = None  # type: ignore[assignment]


def locking_supported() -> bool:
    return fcntl is not None


class OwnerFence:
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
                self.directory / "web-owner.lock",
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise StoreError("locking_unavailable")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd = fd
        except BlockingIOError:
            raise StoreError("runner_busy") from None
        except OSError:
            raise StoreError("locking_unavailable") from None
        finally:
            if fd is not None and self._fd != fd:
                os.close(fd)

    def require(self, directory: Path) -> None:
        if self._fd is None or directory.absolute() != self.directory:
            raise StoreError("owner_lock_required")

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "OwnerFence":
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

"""Non-blocking process locks for a local state ledger on POSIX and Windows.

Keep the lock file in place: unlinking it can let two processes lock different
inodes. This is not a distributed lock; keep SQLite and this file on local disk.
"""
from __future__ import annotations

import errno
import os
from contextlib import contextmanager


def _windows_lock(handle):
    import msvcrt

    # msvcrt locks from the current position. Byte zero is shared by every
    # process, independent of the append position used to initialize the file.
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise RuntimeError("Another digest process is using this state database") from None
        raise

    def unlock():
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    return unlock


def _posix_lock(handle):
    import fcntl

    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("Another digest process is using this state database") from None
    return lambda: fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def exclusive_file_lock(path):
    """Hold an advisory process lock; release even when the body raises."""
    with open(path, "a+b") as handle:
        unlock = _windows_lock(handle) if os.name == "nt" else _posix_lock(handle)
        try:
            yield
        finally:
            unlock()

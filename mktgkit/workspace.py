"""Workspace paths, clocks and recoverable local file transactions."""

from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .errors import MktgError

_TRANSACTION = contextvars.ContextVar("marketing_transaction", default=None)
STATE = ".mktgkit-state"


def scoped(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise MktgError("path must be inside the workspace", path=str(relative))
    return path


def timestamp(now):
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise MktgError(f"invalid ISO date or timestamp {value!r}") from exc
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def text_hash(body):
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    normalized = "\n".join(line.rstrip(" \t") for line in lines).strip("\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def config(root):
    path = scoped(root, "mktgkit.json")
    if not path.is_file():
        raise MktgError(
            "not a marketing workspace", fix="Run mktgkit init CLIENT or pass --workspace CLIENT."
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("name"), str) or not value["name"].strip():
        raise MktgError("name must be nonempty text", path="mktgkit.json")
    return value


def resolve_root(explicit, env):
    base = Path(env.get("CLAUDE_PROJECT_DIR") or ".")
    value = explicit or env.get("MKTGKIT_WORKSPACE")
    return (base / value if value else base).resolve()


def clock(config_data, explicit, env):
    value = explicit or env.get("MKTGKIT_NOW") or config_data.get("now")
    return parse_time(value) if value else datetime.now(timezone.utc)


def _replace(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mktgkit-write-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def atomic_write(path, text):
    path = Path(path).resolve()
    tx = _TRANSACTION.get()
    if tx:
        root, journal, original = tx
        scoped(root, path)
        key = path.relative_to(root).as_posix()
        if key.split("/")[0] == STATE:
            raise MktgError("reserved workspace state path")
        if key not in original:
            original[key] = base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else None
            _replace(journal, json.dumps(original).encode("utf-8"))
    _replace(path, text.encode("utf-8"))


def _recover(root, journal):
    if journal.is_file():
        original = json.loads(journal.read_text(encoding="utf-8"))
        if not isinstance(original, dict):
            raise MktgError("invalid recovery journal", path=STATE)
        for name, value in original.items():
            path = scoped(root, name)
            if not path.relative_to(root).parts or path.relative_to(root).parts[0] == STATE:
                raise MktgError("invalid recovery journal path", path=STATE)
            if value is None:
                path.unlink(missing_ok=True)
            else:
                _replace(path, base64.b64decode(value, validate=True))
        journal.unlink()


@contextlib.contextmanager
def locked(root, *, mutate=False):
    root = Path(root).resolve()
    state = scoped(root, STATE)
    state.mkdir(exist_ok=True)
    lock = scoped(root, state / "lock")
    journal = scoped(root, state / "undo.json")
    with lock.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            if lock.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            _recover(root, journal)
            token = _TRANSACTION.set((root, journal, {}) if mutate else None)
            try:
                yield
                journal.unlink(missing_ok=True)
            except BaseException:
                _recover(root, journal)
                raise
            finally:
                _TRANSACTION.reset(token)
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)

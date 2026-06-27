"""Owner-scoped local session registry for gateway SSH children."""

from __future__ import annotations

import json
import os
import re
import signal
import time
from contextlib import suppress
from pathlib import Path
from typing import Optional

from .paths import runtime_dir

DEFAULT_OWNER_CLEANUP_GRACE_SECONDS = 180


class GatewaySessionRegistry:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else runtime_dir() / "run" / "sessions"

    def cleanup_owner(
        self,
        owner_id: Optional[str],
        stale_after_seconds: int = DEFAULT_OWNER_CLEANUP_GRACE_SECONDS,
        now: Optional[float] = None,
    ) -> list[int]:
        if not owner_id:
            return []
        current = time.time() if now is None else now
        removed: list[int] = []
        owner_dir = self._owner_dir(owner_id)
        for path in owner_dir.glob("*.json"):
            payload = _read_json(path)
            child_pid = _int_or_none(payload.get("child_pid"))
            if child_pid is None:
                _unlink(path)
                continue
            started_at = float(payload.get("started_at", 0) or 0)
            age = current - started_at
            if age < stale_after_seconds:
                continue
            if _pid_exists(child_pid):
                with suppress(ProcessLookupError, PermissionError):
                    os.kill(child_pid, signal.SIGTERM)
            _unlink(path)
            removed.append(child_pid)
        _rmdir_if_empty(owner_dir)
        return removed

    def write(
        self,
        owner_id: Optional[str],
        child_pid: Optional[int],
        mcp_pid: int,
        gateway: str,
        target: str,
        command_sha256: str,
        started_at: Optional[float] = None,
    ) -> Optional[Path]:
        if not owner_id or child_pid is None:
            return None
        path = self._owner_dir(owner_id) / f"{child_pid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "owner_id": owner_id,
            "child_pid": child_pid,
            "mcp_pid": mcp_pid,
            "gateway": gateway,
            "target": target,
            "command_sha256": command_sha256,
            "started_at": time.time() if started_at is None else started_at,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return path

    def remove(self, owner_id: Optional[str], child_pid: Optional[int]) -> None:
        if not owner_id or child_pid is None:
            return
        owner_dir = self._owner_dir(owner_id)
        _unlink(owner_dir / f"{child_pid}.json")
        _rmdir_if_empty(owner_dir)

    def _owner_dir(self, owner_id: str) -> Path:
        return self.root / _safe_owner(owner_id)


def _safe_owner(owner_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", owner_id.strip())
    return safe.strip(".-") or "unknown"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _unlink(path: Path) -> None:
    with suppress(FileNotFoundError):
        path.unlink()


def _rmdir_if_empty(path: Path) -> None:
    with suppress(FileNotFoundError, OSError):
        path.rmdir()


def _int_or_none(value: object) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True

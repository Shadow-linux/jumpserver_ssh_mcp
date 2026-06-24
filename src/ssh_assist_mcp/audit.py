"""JSONL audit logging with sensitive value redaction."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

SENSITIVE_KEYS = {"password", "passwd", "token", "secret", "private_key", "key", "dsn"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if any(item in key.lower() for item in SENSITIVE_KEYS) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AuditLogger:
    def __init__(self, path: Optional[str] = None) -> None:
        default_path = os.environ.get("SSH_ASSIST_AUDIT_LOG", "logs/jumpserver-ssh-mcp-audit.jsonl")
        self.path = Path(path or default_path)

    def record(
        self,
        tool: str,
        target: str,
        risk_level: str,
        params: Dict[str, Any],
        status: str,
        error: Optional[str] = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tool": tool,
            "target": target,
            "risk_level": risk_level,
            "params": redact(params),
            "status": status,
            "error": error,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

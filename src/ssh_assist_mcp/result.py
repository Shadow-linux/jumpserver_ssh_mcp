"""Shared result and audit event models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class CommandResult:
    command: List[str]
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass
class SSHAuditEvent:
    tool: str
    host: str
    sudo: bool
    params: Dict[str, Any]
    risk_level: str

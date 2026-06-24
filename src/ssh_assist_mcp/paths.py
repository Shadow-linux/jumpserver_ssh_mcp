"""Runtime filesystem paths for jumpserver-ssh-mcp."""

from __future__ import annotations

from pathlib import Path


def runtime_dir() -> Path:
    return Path.home() / "jumpserver-ssh-mcp"


def default_profile_path() -> Path:
    return runtime_dir() / "config" / "local.yaml"


def default_profile_candidates() -> list[Path]:
    return [
        default_profile_path(),
        Path("config/local.yaml"),
        Path("config/example.yaml"),
    ]


def default_audit_log_path() -> Path:
    return runtime_dir() / "logs" / "jumpserver-ssh-mcp-audit.jsonl"

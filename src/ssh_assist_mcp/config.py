"""Profile loading and SSH/JumperServer gateway configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .errors import ToolExecutionError
from .paths import default_profile_candidates

DEFAULT_COMMAND_TIMEOUT = 1800


@dataclass
class MatcherConfig:
    name: Optional[str] = None
    path: Optional[str] = None


@dataclass
class PrivilegeEscalationConfig:
    method: str
    command: str = "sudo su -"
    root_prompt_patterns: List[str] = None
    password_prompt_patterns: List[str] = None
    timeout: int = 30


@dataclass
class GatewayConfig:
    name: str
    type: str
    command: str
    target_prompt_patterns: List[str]
    shell_prompt_patterns: List[str]
    account_prompt_patterns: List[str] = None
    preferred_account: Optional[str] = None
    account_id_by_host: Dict[str, str] = None
    login_prompt_patterns: List[str] = None
    login_password_env: Optional[str] = None
    connect_timeout: int = 30
    command_timeout: int = DEFAULT_COMMAND_TIMEOUT
    max_attempts: int = 2
    retry_delay_seconds: float = 0.5
    privilege_escalation: Optional[PrivilegeEscalationConfig] = None
    matcher: MatcherConfig = None


@dataclass
class SSHConfig:
    user: Optional[str] = None
    port: Optional[int] = None
    identity_file: Optional[str] = None
    strict_host_key_checking: Optional[str] = None
    gateways: Dict[str, GatewayConfig] = None
    default_gateway: Optional[str] = None
    matcher_search_paths: List[str] = None

    @classmethod
    def from_profile(cls, profile_data: Dict[str, object]) -> "SSHConfig":
        ssh_section = profile_data.get("ssh", {})
        ssh_section = ssh_section if isinstance(ssh_section, dict) else {}
        defaults = ssh_section.get("defaults", {})
        defaults = defaults if isinstance(defaults, dict) else {}
        matcher_section = profile_data.get("matchers", {})
        matcher_section = matcher_section if isinstance(matcher_section, dict) else {}
        gateways = profile_data.get("gateways", ssh_section.get("gateways", {}))
        default_gateway = profile_data.get("default_gateway", ssh_section.get("default_gateway"))
        port = defaults.get("port")
        return cls(
            user=defaults.get("user"),
            port=int(port) if port is not None else None,
            identity_file=defaults.get("identity_file"),
            strict_host_key_checking=defaults.get("strict_host_key_checking"),
            gateways=_gateway_configs(gateways),
            default_gateway=default_gateway,
            matcher_search_paths=_matcher_search_paths(matcher_section),
        )


def load_ssh_config(path: Optional[str] = None) -> SSHConfig:
    profile_path = _resolve_profile_path(path)
    if not profile_path.exists():
        return SSHConfig(gateways={}, matcher_search_paths=[])
    try:
        import yaml
    except ImportError as exc:
        raise ToolExecutionError("PyYAML is required to load SSH profile defaults.") from exc
    with profile_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return SSHConfig(gateways={}, matcher_search_paths=[])
    return SSHConfig.from_profile(data)


def _resolve_profile_path(path: Optional[str] = None) -> Path:
    explicit_path = path or os.environ.get("SSH_ASSIST_PROFILE")
    if explicit_path:
        return Path(explicit_path)
    for candidate in default_profile_candidates():
        if candidate.exists():
            return candidate
    return default_profile_candidates()[0]


def _gateway_configs(raw_gateways: object) -> Dict[str, GatewayConfig]:
    if not isinstance(raw_gateways, dict):
        return {}
    gateways: Dict[str, GatewayConfig] = {}
    for name, raw in raw_gateways.items():
        if not isinstance(raw, dict):
            continue
        gateways[str(name)] = GatewayConfig(
            name=str(name),
            type=str(raw.get("type", "interactive_expect")),
            command=str(raw["command"]),
            login_prompt_patterns=list(raw.get("login_prompt_patterns", [])),
            login_password_env=raw.get("login_password_env"),
            target_prompt_patterns=list(raw.get("target_prompt_patterns", [r"(?i)host|ip|target"])),
            shell_prompt_patterns=list(raw.get("shell_prompt_patterns", [r"[$#>] "])),
            account_prompt_patterns=list(raw.get("account_prompt_patterns", [])),
            preferred_account=raw.get("preferred_account"),
            account_id_by_host={str(k): str(v) for k, v in (raw.get("account_id_by_host", {}) or {}).items()},
            connect_timeout=int(raw.get("connect_timeout", 30)),
            command_timeout=int(raw.get("command_timeout", DEFAULT_COMMAND_TIMEOUT)),
            max_attempts=int(raw.get("max_attempts", 2)),
            retry_delay_seconds=float(raw.get("retry_delay_seconds", 0.5)),
            privilege_escalation=_privilege_escalation_config(raw.get("privilege_escalation")),
            matcher=_matcher_config(raw.get("matcher", "builtin-generic")),
        )
    return gateways


def _matcher_search_paths(raw: object) -> List[str]:
    if not isinstance(raw, dict):
        return []
    paths = raw.get("custom_dirs", raw.get("search_paths", []))
    return list(paths or [])


def _matcher_config(raw: object) -> MatcherConfig:
    if isinstance(raw, str):
        return MatcherConfig(name=raw)
    if isinstance(raw, dict):
        return MatcherConfig(name=raw.get("name"), path=raw.get("path"))
    return MatcherConfig()


def _privilege_escalation_config(raw: object) -> Optional[PrivilegeEscalationConfig]:
    if not isinstance(raw, dict):
        return None
    method = str(raw.get("method", "")).strip()
    if not method:
        return None
    return PrivilegeEscalationConfig(
        method=method,
        command=str(raw.get("command", "sudo su -")),
        root_prompt_patterns=list(raw.get("root_prompt_patterns", [r"# "])),
        password_prompt_patterns=list(raw.get("password_prompt_patterns", [r"(?i)password", "密码"])),
        timeout=int(raw.get("timeout", 30)),
    )

"""Lightweight safety policy for remote SSH execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .errors import SafetyError

POLICY_VERSION = "2026-06-12"

HIGH_RISK_COMMAND_PATTERNS = {
    "destructive filesystem change": r"(^|[;&|]\s*|\bsudo\s+)(rm|mv|shred|wipefs|mkfs(?:\.\w+)?|truncate|dd)\b",
    "filesystem ownership or mode change": r"(^|[;&|]\s*|\bsudo\s+)(chmod|chown|chgrp)\b",
    "file overwrite or in-place edit": r"(^|[;&|]\s*|\bsudo\s+)(sed\s+-i\b|tee\b)|>{1,2}[ \t]*(?!/dev/null(?:\s|$))[^&\s]",
    "process or service change": (
        r"(^|[;&|]\s*|\bsudo\s+)(kill|killall|pkill|reboot|shutdown|poweroff|halt)\b"
        r"|(^|[;&|]\s*|\bsudo\s+)(systemctl|service)\b[^\n;&|]*(start|stop|restart|enable|disable|mask)\b"
    ),
    "package change": r"(^|[;&|]\s*|\bsudo\s+)(apt(?:-get)?|yum|dnf|rpm|dpkg|brew)\b[^\n;&|]*(install|remove|erase|upgrade|update)\b",
    "network or firewall change": r"(^|[;&|]\s*|\bsudo\s+)(iptables|nft|firewall-cmd|ufw|ip\s+(?:addr|link|route))\b",
    "database write": (
        r"(^|[;&|]\s*|\bsudo\s+)(mysql|psql)\b[^\n;&|]*(insert|update|delete|replace|alter|drop|truncate|create|grant|revoke)\b"
        r"|\b(insert|update|delete|replace|alter|drop|truncate|create|grant|revoke)\b[^\n;&|]*\|\s*(mysql|psql)\b"
    ),
}

EXPENSIVE_READ_PATTERNS = {
    "broad filesystem scan": r"(^|[;&|]\s*|\bsudo\s+)find\s+/(?:\s|$)",
    "recursive grep": r"(^|[;&|]\s*|\bsudo\s+)(grep|rg)\b[^\n;&|]*(?:-R|-r|--recursive)\b",
    "full filesystem disk usage scan": r"(^|[;&|]\s*|\bsudo\s+)du\b[^\n;&|]*(?:\s/|\s/\S*)",
}


@dataclass(frozen=True)
class ToolRiskAssessment:
    tool: str
    risk_level: str
    reason: str
    requires_confirmation: bool = False
    confirmation_fields: list[str] = field(default_factory=list)
    risk_signals: list[str] = field(default_factory=list)

    def audit_params(self) -> Dict[str, Any]:
        return {
            "policy_version": POLICY_VERSION,
            "risk_reason": self.reason,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_fields": self.confirmation_fields,
            "risk_signals": self.risk_signals,
        }


class SafetyPolicy:
    def assess_tool(self, tool: str, params: Optional[Dict[str, Any]] = None) -> ToolRiskAssessment:
        params = params or {}
        if tool == "ssh.run_command":
            return self._assess_command(tool, str(params.get("command", "")), bool(params.get("sudo")))
        if tool == "ssh.run_script":
            signals = self._match(str(params.get("content", "")), HIGH_RISK_COMMAND_PATTERNS)
            if signals:
                return ToolRiskAssessment(
                    tool,
                    "high",
                    "Remote script contains high-risk operations.",
                    True,
                    ["host", "environment", "script purpose", "impact", "rollback"],
                    signals,
                )
            return ToolRiskAssessment(
                tool,
                "medium",
                "Remote script can perform multiple operations and needs review by default.",
                True,
                ["host", "environment", "script purpose", "impact"],
            )
        if tool == "ssh.rsync_upload":
            return ToolRiskAssessment(
                tool,
                "medium",
                "Remote upload can change target filesystem state.",
                True,
                ["host", "local_path", "remote_path", "rollback"],
            )
        if tool == "ssh.rsync_download":
            return ToolRiskAssessment(
                tool,
                "medium",
                "Remote download may copy sensitive data and should stay auditable.",
                True,
                ["host", "remote_path", "local_path"],
            )
        return ToolRiskAssessment(tool, "read", "Read-only operation.")

    def ensure_tool_executable(self, assessment: ToolRiskAssessment, confirmed: bool) -> None:
        if assessment.requires_confirmation and not confirmed:
            raise SafetyError(
                f"{assessment.tool} requires confirmation: {assessment.reason} "
                f"signals={assessment.risk_signals}"
            )

    def _assess_command(self, tool: str, command: str, sudo: bool) -> ToolRiskAssessment:
        high = self._match(command, HIGH_RISK_COMMAND_PATTERNS)
        if high:
            return ToolRiskAssessment(
                tool,
                "high",
                "Remote command contains high-risk operations.",
                True,
                ["host", "environment", "command", "impact", "rollback"],
                high,
            )
        expensive = self._match(command, EXPENSIVE_READ_PATTERNS)
        if expensive:
            return ToolRiskAssessment(
                tool,
                "medium",
                "Remote command may perform an expensive broad read.",
                True,
                ["host", "environment", "command", "impact", "stop condition"],
                expensive,
            )
        if sudo:
            return ToolRiskAssessment(tool, "medium", "Read-only privileged command.", False)
        return ToolRiskAssessment(tool, "read", "Read-only SSH command.")

    def _match(self, value: str, patterns: Dict[str, str]) -> list[str]:
        return [name for name, pattern in patterns.items() if re.search(pattern, value, re.IGNORECASE)]

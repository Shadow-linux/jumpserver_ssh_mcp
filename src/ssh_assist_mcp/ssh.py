"""SSH command, script, and rsync execution helpers."""

from __future__ import annotations

import hashlib
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional

from .audit import AuditLogger
from .config import GatewayConfig, SSHConfig, load_ssh_config
from .errors import SafetyError, ToolExecutionError
from .gateway import GatewaySSHRunner
from .matchers import MatcherRegistry
from .result import CommandResult, SSHAuditEvent
from .safety import SafetyPolicy


class SSHTool:
    def __init__(
        self,
        config: Optional[SSHConfig] = None,
        audit_logger: Optional[AuditLogger] = None,
        safety_policy: Optional[SafetyPolicy] = None,
    ) -> None:
        self.config = config or SSHConfig()
        self.audit_logger = audit_logger or AuditLogger()
        self.safety_policy = safety_policy or SafetyPolicy()

    def run_command(
        self,
        host: str,
        command: str,
        timeout: int = 30,
        cwd: Optional[str] = None,
        sudo: bool = False,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
    ) -> CommandResult:
        privilege_escalation = self._privilege_escalation_method(connection_mode, gateway, sudo)
        remote_command = self._remote_command(command, cwd=cwd, sudo=sudo and privilege_escalation != "sudo_su")
        assessment = self.safety_policy.assess_tool(
            "ssh.run_command",
            {"command": command, "sudo": sudo, "connection_mode": connection_mode, "gateway": gateway},
        )
        audit_event = self._audit_event(
            "ssh.run_command",
            host,
            sudo,
            assessment,
            {
                "command_preview": _preview(command),
                "command_sha256": _sha256(command),
                "connection_mode": connection_mode,
                "cwd": cwd,
                "gateway": gateway,
                "privilege_escalation": privilege_escalation,
                "timeout": timeout,
            },
        )
        self._ensure_executable(assessment, confirmed, audit_event)
        if connection_mode == "gateway":
            gateway_config = self._gateway_config(gateway)
            return GatewaySSHRunner(gateway_config, matcher_registry=self._matcher_registry()).run_command(
                host, remote_command, timeout, audit_event, self._record_audit
            )
        return self._run(["ssh", *self._ssh_options(), self._target(host), remote_command], timeout, audit_event)

    def matcher_probe(self, host: str, gateway: Optional[str] = None, timeout: int = 60) -> dict:
        gateway_config = self._gateway_config(gateway)
        return GatewaySSHRunner(gateway_config, matcher_registry=self._matcher_registry()).probe(host, timeout)

    def run_script(
        self,
        host: str,
        script_type: str,
        content: str,
        args: Optional[List[str]] = None,
        timeout: int = 300,
        sudo: bool = False,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
    ) -> CommandResult:
        interpreter = "python3" if script_type == "python" else "bash"
        remote = f"{interpreter} -s"
        privilege_escalation = self._privilege_escalation_method(connection_mode, gateway, sudo)
        if sudo and privilege_escalation != "sudo_su":
            remote = f"sudo -n {remote}"
        argv = ["ssh", *self._ssh_options(), self._target(host), remote]
        if args:
            argv.extend(args)
        assessment = self.safety_policy.assess_tool(
            "ssh.run_script",
            {
                "sudo": sudo,
                "connection_mode": connection_mode,
                "gateway": gateway,
                "script_type": script_type,
                "content": content,
            },
        )
        audit_event = self._audit_event(
            "ssh.run_script",
            host,
            sudo,
            assessment,
            {
                "connection_mode": connection_mode,
                "script_type": script_type,
                "content_sha256": _sha256(content),
                "content_bytes": len(content.encode("utf-8")),
                "args_count": len(args or []),
                "gateway": gateway,
                "privilege_escalation": privilege_escalation,
                "timeout": timeout,
            },
        )
        self._ensure_executable(assessment, confirmed, audit_event)
        if connection_mode == "gateway":
            gateway_config = self._gateway_config(gateway)
            gateway_command = self._script_gateway_command(
                script_type, content, args or [], sudo=sudo and privilege_escalation != "sudo_su"
            )
            return GatewaySSHRunner(gateway_config, matcher_registry=self._matcher_registry()).run_command(
                host, gateway_command, timeout, audit_event, self._record_audit
            )
        return self._run(argv, timeout, audit_event, input_text=content)

    def rsync_upload(
        self,
        host: str,
        local_path: str,
        remote_path: str,
        timeout: int = 300,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
    ) -> CommandResult:
        if connection_mode == "gateway":
            raise ToolExecutionError("rsync over interactive gateway is not supported.")
        return self._rsync(
            "ssh.rsync_upload",
            ["rsync", "-az", "-e", self._rsync_ssh_command(), local_path, f"{self._target(host)}:{remote_path}"],
            host,
            timeout,
            confirmed,
            {"connection_mode": connection_mode, "gateway": gateway, "local_path": local_path, "remote_path": remote_path},
        )

    def rsync_download(
        self,
        host: str,
        remote_path: str,
        local_path: str,
        timeout: int = 300,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
    ) -> CommandResult:
        if connection_mode == "gateway":
            raise ToolExecutionError("rsync over interactive gateway is not supported.")
        return self._rsync(
            "ssh.rsync_download",
            ["rsync", "-az", "-e", self._rsync_ssh_command(), f"{self._target(host)}:{remote_path}", local_path],
            host,
            timeout,
            confirmed,
            {"connection_mode": connection_mode, "gateway": gateway, "remote_path": remote_path, "local_path": local_path},
        )

    def _rsync(self, tool: str, argv: List[str], host: str, timeout: int, confirmed: bool, params: Dict[str, Any]):
        assessment = self.safety_policy.assess_tool(tool, params)
        audit_event = self._audit_event(tool, host, False, assessment, {**params, "timeout": timeout})
        self._ensure_executable(assessment, confirmed, audit_event)
        return self._run(argv, timeout, audit_event)

    def _run(
        self,
        command: List[str],
        timeout: int,
        audit_event: Optional[SSHAuditEvent] = None,
        input_text: Optional[str] = None,
    ) -> CommandResult:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command, input=input_text, text=True, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.SubprocessError as exc:
            self._record_audit(audit_event, "error", time.monotonic() - started, error=str(exc))
            raise ToolExecutionError(str(exc)) from exc
        result = CommandResult(command, completed.returncode, completed.stdout, completed.stderr)
        status = "success" if completed.returncode == 0 else "failed"
        self._record_audit(audit_event, status, time.monotonic() - started, returncode=completed.returncode)
        return result

    def _ensure_executable(self, assessment, confirmed: bool, audit_event: SSHAuditEvent) -> None:
        try:
            self.safety_policy.ensure_tool_executable(assessment, confirmed)
        except SafetyError as exc:
            self._record_audit(audit_event, "blocked", 0, error=str(exc))
            raise

    def _audit_event(self, tool: str, host: str, sudo: bool, assessment, params: Dict[str, Any]) -> SSHAuditEvent:
        return SSHAuditEvent(
            tool=tool,
            host=host,
            sudo=sudo,
            risk_level=assessment.risk_level,
            params={**assessment.audit_params(), **params},
        )

    def _record_audit(
        self,
        audit_event: Optional[SSHAuditEvent],
        status: str,
        duration_seconds: float,
        returncode: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        if audit_event is None:
            return
        params = dict(audit_event.params)
        params.update({"sudo": audit_event.sudo, "duration_ms": int(duration_seconds * 1000), "returncode": returncode})
        self.audit_logger.record(audit_event.tool, audit_event.host, audit_event.risk_level, params, status, error)

    def _ssh_options(self) -> List[str]:
        options: List[str] = []
        if self.config.port:
            options.extend(["-p", str(self.config.port)])
        if self.config.identity_file:
            options.extend(["-i", self.config.identity_file])
        if self.config.strict_host_key_checking is not None:
            options.extend(["-o", f"StrictHostKeyChecking={self.config.strict_host_key_checking}"])
        return options

    def _rsync_ssh_command(self) -> str:
        return " ".join(shlex.quote(item) for item in ["ssh", *self._ssh_options()])

    def _target(self, host: str) -> str:
        return f"{self.config.user}@{host}" if self.config.user else host

    def _remote_command(self, command: str, cwd: Optional[str], sudo: bool) -> str:
        parts = []
        if cwd:
            parts.append(f"cd {shlex.quote(cwd)}")
        parts.append(command)
        remote = " && ".join(parts)
        if sudo:
            remote = f"sudo -n sh -lc {shlex.quote(remote)}"
        return remote

    def _script_gateway_command(self, script_type: str, content: str, args: List[str], sudo: bool) -> str:
        interpreter = "python3" if script_type == "python" else "bash"
        quoted_args = " ".join(shlex.quote(item) for item in args)
        argv = f"{interpreter} -s" + (f" -- {quoted_args}" if quoted_args else "")
        if sudo:
            argv = f"sudo -n {argv}"
        delimiter = "__SSH_ASSIST_SCRIPT__"
        return f"{argv} <<'{delimiter}'\n{content}\n{delimiter}"

    def _privilege_escalation_method(self, connection_mode: str, gateway: Optional[str], sudo: bool) -> Optional[str]:
        if not sudo or connection_mode != "gateway":
            return None
        escalation = self._gateway_config(gateway).privilege_escalation
        return escalation.method if escalation else None

    def _gateway_config(self, gateway: Optional[str]) -> GatewayConfig:
        gateway = gateway or self.config.default_gateway
        if not gateway:
            raise ToolExecutionError("gateway is required when connection_mode=gateway.")
        gateways = self.config.gateways or {}
        if gateway not in gateways:
            raise ToolExecutionError(f"Unknown SSH gateway: {gateway}")
        gateway_config = gateways[gateway]
        if gateway_config.type != "interactive_expect":
            raise ToolExecutionError(f"Unsupported SSH gateway adapter type: {gateway_config.type}")
        return gateway_config

    def _matcher_registry(self) -> MatcherRegistry:
        return MatcherRegistry(search_paths=self.config.matcher_search_paths or [])


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _preview(value: str, limit: int = 160) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."

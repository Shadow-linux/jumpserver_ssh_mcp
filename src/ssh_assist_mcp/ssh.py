"""SSH command, script, rsync, and portable file transfer helpers."""

from __future__ import annotations

import base64
import hashlib
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import AuditLogger
from .config import DEFAULT_COMMAND_TIMEOUT, GatewayConfig, SSHConfig, load_ssh_config
from .errors import SafetyError, ToolExecutionError
from .gateway import GatewaySSHRunner
from .matchers import MatcherRegistry
from .result import CommandResult, SSHAuditEvent
from .safety import SafetyPolicy

DEFAULT_FILE_TRANSFER_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_FILE_TRANSFER_CHUNK_SIZE = 768 * 1024
FILE_TRANSFER_HEREDOC = "__SSH_ASSIST_B64__"


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
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        cwd: Optional[str] = None,
        sudo: bool = False,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
        owner_id: Optional[str] = None,
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
                "owner_id": owner_id,
                "privilege_escalation": privilege_escalation,
                "timeout": timeout,
            },
        )
        self._ensure_executable(assessment, confirmed, audit_event)
        if connection_mode == "gateway":
            gateway_config = self._gateway_config(gateway)
            return GatewaySSHRunner(gateway_config, matcher_registry=self._matcher_registry()).run_command(
                host, remote_command, timeout, audit_event, self._record_audit, owner_id=owner_id
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
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        sudo: bool = False,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
        owner_id: Optional[str] = None,
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
                "owner_id": owner_id,
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
                host, gateway_command, timeout, audit_event, self._record_audit, owner_id=owner_id
            )
        return self._run(argv, timeout, audit_event, input_text=content)

    def rsync_upload(
        self,
        host: str,
        local_path: str,
        remote_path: str,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> CommandResult:
        if connection_mode == "gateway":
            raise ToolExecutionError("rsync over interactive gateway is not supported.")
        return self._rsync(
            "ssh.rsync_upload",
            ["rsync", "-az", "-e", self._rsync_ssh_command(), local_path, f"{self._target(host)}:{remote_path}"],
            host,
            timeout,
            confirmed,
            {
                "connection_mode": connection_mode,
                "gateway": gateway,
                "owner_id": owner_id,
                "local_path": local_path,
                "remote_path": remote_path,
            },
        )

    def rsync_download(
        self,
        host: str,
        remote_path: str,
        local_path: str,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> CommandResult:
        if connection_mode == "gateway":
            raise ToolExecutionError("rsync over interactive gateway is not supported.")
        return self._rsync(
            "ssh.rsync_download",
            ["rsync", "-az", "-e", self._rsync_ssh_command(), f"{self._target(host)}:{remote_path}", local_path],
            host,
            timeout,
            confirmed,
            {
                "connection_mode": connection_mode,
                "gateway": gateway,
                "owner_id": owner_id,
                "remote_path": remote_path,
                "local_path": local_path,
            },
        )

    def file_push(
        self,
        host: str,
        local_path: str,
        remote_path: str,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
        owner_id: Optional[str] = None,
        max_bytes: int = DEFAULT_FILE_TRANSFER_MAX_BYTES,
        chunk_size: int = DEFAULT_FILE_TRANSFER_CHUNK_SIZE,
    ) -> Dict[str, Any]:
        local = Path(local_path).expanduser()
        if not local.is_file():
            raise ToolExecutionError(f"local_path is not a file: {local_path}")
        size = local.stat().st_size
        if size > max_bytes:
            raise ToolExecutionError(f"local file size {size} exceeds max_bytes {max_bytes}")
        digest = _file_sha256(local)
        assessment = self.safety_policy.assess_tool(
            "ssh.file_push",
            {
                "connection_mode": connection_mode,
                "gateway": gateway,
                "owner_id": owner_id,
                "local_path": str(local),
                "remote_path": remote_path,
                "bytes": size,
                "sha256": digest,
            },
        )
        audit_event = self._audit_event(
            "ssh.file_push",
            host,
            False,
            assessment,
            {
                "connection_mode": connection_mode,
                "gateway": gateway,
                "owner_id": owner_id,
                "local_path": str(local),
                "remote_path": remote_path,
                "bytes": size,
                "sha256": digest,
                "max_bytes": max_bytes,
                "chunk_size": chunk_size,
                "timeout": timeout,
            },
        )
        self._ensure_executable(assessment, confirmed, audit_event)
        started = time.monotonic()
        try:
            tmp_b64 = f"{remote_path}.ssh-assist-{digest[:12]}.b64"
            remote_dir = _remote_dirname(remote_path)
            self._execute_remote_command(
                host,
                f"mkdir -p {shlex.quote(remote_dir)} && : > {shlex.quote(tmp_b64)}",
                timeout,
                connection_mode,
                gateway,
                owner_id,
            )
            effective_chunk_size = _base64_chunk_size(chunk_size)
            with local.open("rb") as handle:
                while True:
                    chunk = handle.read(effective_chunk_size)
                    if not chunk:
                        break
                    encoded = base64.b64encode(chunk).decode("ascii")
                    append_command = (
                        f"cat >> {shlex.quote(tmp_b64)} <<'{FILE_TRANSFER_HEREDOC}'\n"
                        f"{encoded}\n"
                        f"{FILE_TRANSFER_HEREDOC}"
                    )
                    self._execute_remote_command(host, append_command, timeout, connection_mode, gateway, owner_id)
            finalize_command = (
                f"base64 -d {shlex.quote(tmp_b64)} > {shlex.quote(remote_path)} && "
                f"rm -f {shlex.quote(tmp_b64)} && "
                f"sha256sum {shlex.quote(remote_path)} | awk '{{print $1}}'"
            )
            remote_digest = _first_output_token(
                self._execute_remote_command(host, finalize_command, timeout, connection_mode, gateway, owner_id).stdout
            )
            if remote_digest != digest:
                raise ToolExecutionError(f"remote sha256 mismatch: expected {digest}, got {remote_digest}")
            self._record_audit(audit_event, "success", time.monotonic() - started, returncode=0)
            return {
                "direction": "push",
                "host": host,
                "connection_mode": connection_mode,
                "gateway": gateway,
                "local_path": str(local),
                "remote_path": remote_path,
                "bytes": size,
                "sha256": digest,
                "verified": True,
            }
        except Exception as exc:
            self._record_audit(audit_event, "error", time.monotonic() - started, error=str(exc))
            if isinstance(exc, ToolExecutionError):
                raise
            raise ToolExecutionError(str(exc)) from exc

    def file_pull(
        self,
        host: str,
        remote_path: str,
        local_path: str,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        confirmed: bool = False,
        connection_mode: str = "direct",
        gateway: Optional[str] = None,
        owner_id: Optional[str] = None,
        max_bytes: int = DEFAULT_FILE_TRANSFER_MAX_BYTES,
    ) -> Dict[str, Any]:
        assessment = self.safety_policy.assess_tool(
            "ssh.file_pull",
            {
                "connection_mode": connection_mode,
                "gateway": gateway,
                "owner_id": owner_id,
                "remote_path": remote_path,
                "local_path": local_path,
            },
        )
        audit_event = self._audit_event(
            "ssh.file_pull",
            host,
            False,
            assessment,
            {
                "connection_mode": connection_mode,
                "gateway": gateway,
                "owner_id": owner_id,
                "remote_path": remote_path,
                "local_path": str(Path(local_path).expanduser()),
                "max_bytes": max_bytes,
                "timeout": timeout,
            },
        )
        self._ensure_executable(assessment, confirmed, audit_event)
        started = time.monotonic()
        try:
            size_output = self._execute_remote_command(
                host, f"wc -c < {shlex.quote(remote_path)}", timeout, connection_mode, gateway, owner_id
            ).stdout.strip()
            size = int(size_output.splitlines()[-1].strip())
            if size > max_bytes:
                raise ToolExecutionError(f"remote file size {size} exceeds max_bytes {max_bytes}")
            remote_digest = _first_output_token(
                self._execute_remote_command(
                    host,
                    f"sha256sum {shlex.quote(remote_path)} | awk '{{print $1}}'",
                    timeout,
                    connection_mode,
                    gateway,
                    owner_id,
                ).stdout
            )
            encoded = self._execute_remote_command(
                host, f"base64 < {shlex.quote(remote_path)}", timeout, connection_mode, gateway, owner_id
            ).stdout
            data = base64.b64decode("".join(encoded.split()), validate=False)
            digest = hashlib.sha256(data).hexdigest()
            if digest != remote_digest:
                raise ToolExecutionError(f"local sha256 mismatch: expected {remote_digest}, got {digest}")
            local = Path(local_path).expanduser()
            local.parent.mkdir(parents=True, exist_ok=True)
            tmp_local = local.with_name(f"{local.name}.ssh-assist-tmp")
            tmp_local.write_bytes(data)
            tmp_local.replace(local)
            audit_event.params.update({"bytes": size, "sha256": digest})
            self._record_audit(audit_event, "success", time.monotonic() - started, returncode=0)
            return {
                "direction": "pull",
                "host": host,
                "connection_mode": connection_mode,
                "gateway": gateway,
                "remote_path": remote_path,
                "local_path": str(local),
                "bytes": size,
                "sha256": digest,
                "verified": True,
            }
        except Exception as exc:
            self._record_audit(audit_event, "error", time.monotonic() - started, error=str(exc))
            if isinstance(exc, ToolExecutionError):
                raise
            raise ToolExecutionError(str(exc)) from exc

    def _rsync(self, tool: str, argv: List[str], host: str, timeout: int, confirmed: bool, params: Dict[str, Any]):
        assessment = self.safety_policy.assess_tool(tool, params)
        audit_event = self._audit_event(tool, host, False, assessment, {**params, "timeout": timeout})
        self._ensure_executable(assessment, confirmed, audit_event)
        return self._run(argv, timeout, audit_event)

    def _execute_remote_command(
        self,
        host: str,
        command: str,
        timeout: int,
        connection_mode: str,
        gateway: Optional[str],
        owner_id: Optional[str] = None,
    ) -> CommandResult:
        if connection_mode == "gateway":
            gateway_config = self._gateway_config(gateway)
            result = GatewaySSHRunner(gateway_config, matcher_registry=self._matcher_registry()).run_command(
                host, command, timeout, None, self._record_audit, owner_id=owner_id
            )
            _ensure_remote_command_succeeded(result)
            return result
        if connection_mode != "direct":
            raise ToolExecutionError(f"Unsupported connection_mode: {connection_mode}")
        result = self._run(["ssh", *self._ssh_options(), self._target(host), command], timeout, None)
        _ensure_remote_command_succeeded(result)
        return result

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
        except subprocess.TimeoutExpired as exc:
            stderr = _coerce_timeout_output(exc.stderr)
            message = f"command timed out after {timeout} seconds"
            if stderr:
                message = f"{message}\n{stderr}"
            self._record_audit(audit_event, "timeout", time.monotonic() - started, returncode=124, error=message)
            return CommandResult(command, 124, _coerce_timeout_output(exc.stdout), message)
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_timeout_output(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _ensure_remote_command_succeeded(result: CommandResult) -> None:
    if result.returncode == 0:
        return
    detail = result.stderr.strip() or result.stdout.strip()
    message = f"remote command failed with returncode {result.returncode}"
    if detail:
        message = f"{message}: {detail}"
    raise ToolExecutionError(message)


def _base64_chunk_size(chunk_size: int) -> int:
    if chunk_size < 3:
        return 3
    return chunk_size - (chunk_size % 3)


def _first_output_token(value: str) -> str:
    parts = value.strip().split()
    return parts[0] if parts else ""


def _remote_dirname(path: str) -> str:
    if "/" not in path.strip("/"):
        return "."
    parent = path.rsplit("/", 1)[0]
    return parent or "/"


def _preview(value: str, limit: int = 160) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."

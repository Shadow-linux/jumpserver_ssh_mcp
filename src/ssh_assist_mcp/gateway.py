"""Interactive SSH gateway runner for JumpServer-style bastions."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import time
from typing import List, Optional, Tuple

from .config import GatewayConfig
from .errors import ToolExecutionError
from .jumpserver_accounts import _select_account_id
from .matchers import MatcherContext, MatcherRegistry
from .result import CommandResult, SSHAuditEvent


class GatewaySSHRunner:
    def __init__(self, config: GatewayConfig, matcher_registry: Optional[MatcherRegistry] = None) -> None:
        self.config = config
        self.matcher_registry = matcher_registry or MatcherRegistry()

    def probe(self, host: str, timeout: int) -> dict:
        child = None
        try:
            child = self._spawn(timeout)
            self._login(child)
            steps = self._drive_matcher_login(child, host, collect_trace=True)
            child.send("exit\r")
            child.close(force=True)
            return {
                "gateway": self.config.name,
                "host": host,
                "matcher": self.config.matcher.name if self.config.matcher else None,
                "shell_reached": bool(steps and steps[-1]["action"]["type"] == "shell_reached"),
                "steps": steps,
            }
        except Exception as exc:
            if child is not None:
                try:
                    child.close(force=True)
                except Exception:
                    pass
            raise ToolExecutionError(str(exc)) from exc

    def run_command(self, host: str, command: str, timeout: int, audit_event: SSHAuditEvent, audit_recorder) -> CommandResult:
        started = time.monotonic()
        sentinel = f"__SSH_ASSIST_DONE_{_sha256(host + command)[:12]}__"
        wrapped = self._wrap_command(command, sentinel)
        last_error: Optional[Exception] = None
        attempts = max(1, int(self.config.max_attempts))
        for attempt in range(1, attempts + 1):
            try:
                stdout, returncode = self._run_once(host, wrapped, command, sentinel, timeout, audit_event.sudo)
                result = CommandResult(
                    [self.config.command, "<gateway>", host, "<remote-command>"], returncode, stdout, ""
                )
                audit_recorder(audit_event, "success" if returncode == 0 else "failed", time.monotonic() - started, returncode)
                return result
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                time.sleep(float(self.config.retry_delay_seconds))
        audit_recorder(audit_event, "error", time.monotonic() - started, error=str(last_error))
        raise ToolExecutionError(str(last_error)) from last_error

    def _run_once(
        self, host: str, wrapped: str, original_command: str, sentinel: str, timeout: int, sudo: bool = False
    ) -> Tuple[str, int]:
        child = None
        try:
            child = self._spawn(timeout)
            self._login(child)
            self._drive_matcher_login(child, host)
            if sudo and self.config.privilege_escalation:
                self._enter_privileged_shell(child)
            child.send(_gateway_input(wrapped))
            child.expect(fr"{sentinel}:END:(\d+)", timeout=timeout)
            stdout = child.before
            returncode = int(child.match.group(1))
            child.send("exit\r")
            if sudo and self.config.privilege_escalation:
                child.send("exit\r")
            child.close(force=True)
            return _clean_gateway_output(stdout, original_command, sentinel), returncode
        except Exception as exc:
            if child is not None:
                try:
                    child.close(force=True)
                except Exception:
                    pass
            raise ToolExecutionError(str(exc)) from exc

    def _spawn(self, timeout: int):
        try:
            import pexpect
        except ImportError as exc:
            raise ToolExecutionError("pexpect is required for interactive SSH gateways.") from exc
        argv = shlex.split(self.config.command)
        if not argv:
            raise ToolExecutionError(f"Gateway {self.config.name} command is empty.")
        return pexpect.spawn(argv[0], argv[1:], encoding="utf-8", timeout=timeout, echo=False)

    def _login(self, child) -> None:
        login_patterns = self.config.login_prompt_patterns or []
        if not login_patterns:
            return
        shell_patterns = self.config.target_prompt_patterns or []
        matched = child.expect([*login_patterns, *shell_patterns], timeout=self.config.connect_timeout)
        if matched >= len(login_patterns):
            return
        if not self.config.login_password_env:
            raise ToolExecutionError(f"Gateway {self.config.name} requested a password but login_password_env is not set.")
        password = os.environ.get(self.config.login_password_env)
        if not password:
            raise ToolExecutionError(f"Environment variable {self.config.login_password_env} is not set.")
        child.send(f"{password}\r")

    def _expect_any(self, child, patterns: List[str], timeout: int) -> None:
        if not patterns:
            raise ToolExecutionError(f"Gateway {self.config.name} has no prompt patterns configured.")
        child.expect(patterns, timeout=timeout)

    def _expect_shell_or_select_account(self, child, host: str) -> None:
        shell_patterns = self.config.shell_prompt_patterns or []
        account_patterns = self.config.account_prompt_patterns or []
        if not shell_patterns:
            raise ToolExecutionError(f"Gateway {self.config.name} has no shell prompt patterns configured.")
        patterns = [*account_patterns, *shell_patterns]
        matched = child.expect(patterns, timeout=self.config.connect_timeout)
        if matched >= len(account_patterns):
            matched_text = f"{child.before}{getattr(child, 'after', '')}"
            if not _matches_any(account_patterns, matched_text):
                return
            account_table = matched_text
            account_id = _select_account_id(self.config, host, account_table)
            child.send(f"{account_id}\r")
            self._expect_any(child, shell_patterns, self.config.connect_timeout)
            return
        account_table = child.before
        account_id = _select_account_id(self.config, host, account_table)
        child.send(f"{account_id}\r")
        self._expect_any(child, shell_patterns, self.config.connect_timeout)

    def _drive_matcher_login(self, child, host: str, collect_trace: bool = False) -> List[dict]:
        matcher_name = self.config.matcher.name if self.config.matcher and self.config.matcher.name else None
        patterns = self.matcher_registry.expect_patterns(matcher_name)
        if not patterns:
            raise ToolExecutionError(f"Gateway {self.config.name} matcher has no prompt patterns configured.")
        context = MatcherContext(host=host, preferred_account=self.config.preferred_account, gateway=self.config.name)
        transcript = ""
        steps: List[dict] = []
        for _ in range(20):
            child.expect(patterns, timeout=self.config.connect_timeout)
            screen = f"{child.before}{getattr(child, 'after', '')}"
            transcript = (transcript + screen)[-12000:]
            result = self.matcher_registry.match(transcript, context, matcher_name=matcher_name)
            if not result.matched:
                raise ToolExecutionError(
                    f"Gateway {self.config.name} matcher could not handle state {result.last_state}: {result.reason}"
                )
            if result.action is None:
                raise ToolExecutionError(f"Gateway {self.config.name} matcher returned no action.")
            steps.append(
                {
                    "matcher": result.matcher,
                    "matched": result.matched,
                    "last_state": result.last_state,
                    "action": {"type": result.action.type, "value": result.action.value},
                }
            )
            if result.action.type == "shell_reached":
                return steps
            if result.action.type == "wait":
                continue
            if result.action.type == "send_text":
                child.send(f"{result.action.value}\r")
                transcript = ""
                continue
            raise ToolExecutionError(f"Unsupported matcher action: {result.action.type}")
        raise ToolExecutionError(f"Gateway {self.config.name} matcher exceeded maximum login steps.")

    def _enter_privileged_shell(self, child) -> None:
        escalation = self.config.privilege_escalation
        if escalation is None:
            return
        if escalation.method != "sudo_su":
            raise ToolExecutionError(f"Unsupported privilege escalation method: {escalation.method}")
        child.send(_gateway_input(escalation.command))
        root_patterns = escalation.root_prompt_patterns or [r"# "]
        password_patterns = escalation.password_prompt_patterns or [r"(?i)password", "密码"]
        matched = child.expect([*root_patterns, *password_patterns], timeout=escalation.timeout)
        if matched >= len(root_patterns):
            raise ToolExecutionError(f"Privilege escalation command requested a password: {escalation.command}")

    def _wrap_command(self, command: str, sentinel: str) -> str:
        return (
            '__ssh_assist_out=$(mktemp /tmp/ssh_assist.XXXXXX)\n'
            f"(\n{command}\n) >\"$__ssh_assist_out\" 2>&1\n"
            "__ssh_assist_rc=$?\n"
            f"printf '\\n{sentinel}:BEGIN\\n'\n"
            'cat "$__ssh_assist_out"\n'
            'rm -f "$__ssh_assist_out"\n'
            f"printf '\\n{sentinel}:END:%s\\n' $__ssh_assist_rc\n"
        )


def _matches_any(patterns: List[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _gateway_input(value: str) -> str:
    return value.replace("\r\n", "\n") + "\r"


def _clean_gateway_output(stdout: str, command: str, sentinel: str) -> str:
    text = _apply_backspaces(_strip_ansi(stdout)).replace("\r", "")
    begin_marker = f"{sentinel}:BEGIN"
    if begin_marker in text:
        text = text.split(begin_marker, 1)[1]
    ordered_command_lines = [line.strip() for line in command.splitlines() if line.strip()]
    command_lines = set(ordered_command_lines)
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if sentinel in stripped or re.search(r"(?i)__ssh_assist_", stripped):
            continue
        if _looks_like_shell_prompt_line(stripped):
            continue
        if stripped in {"(", ")"} or stripped in command_lines:
            continue
        if stripped.startswith("> "):
            continue
        if _looks_like_prompt_echo(stripped):
            continue
        cleaned_lines.append(line.rstrip())
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned + ("\n" if cleaned else "")


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07", "", value)


def _apply_backspaces(value: str) -> str:
    output: List[str] = []
    for char in value:
        if char == "\b":
            if output:
                output.pop()
        else:
            output.append(char)
    return "".join(output)


def _looks_like_shell_prompt_line(value: str) -> bool:
    return bool(re.match(r"^[\w.@:/~\-\[\]() ]+[$#>]\s*$", value))


def _looks_like_prompt_echo(value: str) -> bool:
    return bool(re.match(r"^[\w.@:/~\-\[\]() ]+[$#>]\s+", value))

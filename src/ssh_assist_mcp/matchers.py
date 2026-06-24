"""JumpServer entry matcher plugin contract and registry."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import GatewayConfig
from .errors import ToolExecutionError
from .jumpserver_accounts import _parse_account_options, _select_account_id


@dataclass
class MatcherContext:
    host: str
    preferred_account: Optional[str] = None
    gateway: Optional[str] = None


@dataclass
class MatcherAction:
    type: str
    value: Optional[str] = None


@dataclass
class MatcherResult:
    matcher: str
    matched: bool
    action: Optional[MatcherAction] = None
    last_state: str = "unknown"
    reason: Optional[str] = None
    transcript_excerpt: Optional[str] = None


class DeclarativeMatcher:
    def __init__(self, definition: Dict[str, object], source: Optional[str] = None) -> None:
        errors = validate_declarative_matcher(definition)
        if errors:
            location = f" in {source}" if source else ""
            raise ValueError(f"Invalid matcher{location}: {'; '.join(errors)}")
        self.name = str(definition["name"])
        self.source = source
        self.menu_prompt_patterns = list(definition.get("menu_prompt_patterns", []))
        self.menu_action_value = definition.get("menu_action_value")
        self.target_prompt_patterns = list(definition.get("target_prompt_patterns", []))
        self.host_candidate_patterns = list(definition.get("host_candidate_patterns", []))
        self.account_prompt_patterns = list(definition.get("account_prompt_patterns", []))
        self.shell_prompt_patterns = list(definition.get("shell_prompt_patterns", []))

    def match(self, screen: str, context: MatcherContext) -> MatcherResult:
        if self.account_prompt_patterns and _matches_any(self.account_prompt_patterns, screen):
            return self._account_result(screen, context)

        if self.menu_prompt_patterns and _matches_any(self.menu_prompt_patterns, screen):
            return MatcherResult(self.name, True, MatcherAction("send_text", str(self.menu_action_value)), "menu_prompt")

        if self.host_candidate_patterns and _matches_any(self.host_candidate_patterns, screen):
            return MatcherResult(self.name, True, MatcherAction("send_text", context.host), "host_candidates")

        if self.target_prompt_patterns and _matches_any(self.target_prompt_patterns, screen):
            return MatcherResult(self.name, True, MatcherAction("send_text", context.host), "target_prompt")

        if _parse_account_options(screen):
            return self._account_result(screen, context)

        if self.shell_prompt_patterns and _matches_any(self.shell_prompt_patterns, screen):
            return MatcherResult(self.name, True, MatcherAction("shell_reached"), "shell")

        return MatcherResult(
            self.name,
            False,
            last_state="unknown",
            reason="screen did not match this matcher",
            transcript_excerpt=_redacted_excerpt(screen),
        )

    def _account_result(self, screen: str, context: MatcherContext) -> MatcherResult:
        if not re.search(r"ID>\s*$", screen):
            return MatcherResult(self.name, True, MatcherAction("wait"), "account_prompt")
        try:
            config = GatewayConfig(
                name=context.gateway or self.name,
                type="interactive_expect",
                command="matcher-probe",
                target_prompt_patterns=[],
                shell_prompt_patterns=[],
                account_prompt_patterns=[],
                preferred_account=context.preferred_account,
            )
            account_id = _select_account_id(config, context.host, screen)
        except ToolExecutionError as exc:
            return MatcherResult(
                self.name,
                False,
                last_state="account_prompt",
                reason=str(exc),
                transcript_excerpt=_redacted_excerpt(screen),
            )
        return MatcherResult(self.name, True, MatcherAction("send_text", account_id), "account_prompt")


class BuiltinJumpServerMatcher(DeclarativeMatcher):
    def __init__(self) -> None:
        super().__init__(
            {
                "name": "builtin-generic",
                "target_prompt_patterns": [
                    r"(?i)(input|please).*(host|ip|hostname|asset)",
                    r"(?i)enter\s+(host|ip|hostname|asset)[:> ]*$",
                    r"请输入.*(主机|资产|IP|ip)",
                    r"Opt>\s*$",
                    r"\[Host\]>\s*$",
                ],
                "host_candidate_patterns": [
                    r"(?i)(select|choose).*(host|asset|server)",
                    r"(选择|请选择).*(主机|资产|服务器)",
                ],
                "account_prompt_patterns": [
                    r"(?i)(account|user).*id",
                    r"(账号|账户).*ID",
                    r"输入资产.*账号ID",
                    r"ID>\s*$",
                ],
                "shell_prompt_patterns": [r"[$#>]\s*$"],
            },
            source="builtin",
        )


class MatcherRegistry:
    def __init__(self, search_paths: Optional[Iterable[str]] = None, builtins: Optional[Iterable[DeclarativeMatcher]] = None):
        self._matchers: Dict[str, DeclarativeMatcher] = {}
        for matcher in builtins or [BuiltinJumpServerMatcher()]:
            self._add(matcher)
        for matcher in _load_packaged_reference_matchers():
            self._add(matcher)
        for matcher in _load_matchers(search_paths or []):
            self._add(matcher)

    def list(self) -> List[str]:
        return sorted(self._matchers)

    def get(self, name: str) -> DeclarativeMatcher:
        try:
            return self._matchers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown matcher: {name}") from exc

    def expect_patterns(self, matcher_name: Optional[str] = None) -> List[str]:
        matchers = [self.get(matcher_name)] if matcher_name else self._matchers.values()
        patterns: List[str] = []
        for matcher in matchers:
            patterns.extend(matcher.menu_prompt_patterns)
            patterns.extend(matcher.target_prompt_patterns)
            patterns.extend(matcher.host_candidate_patterns)
            patterns.extend(matcher.account_prompt_patterns)
            patterns.extend(matcher.shell_prompt_patterns)
        return patterns

    def match(self, screen: str, context: MatcherContext, matcher_name: Optional[str] = None) -> MatcherResult:
        if matcher_name:
            return self.get(matcher_name).match(screen, context)
        failures: List[str] = []
        for matcher in self._matchers.values():
            result = matcher.match(screen, context)
            if result.matched:
                return result
            failures.append(f"{matcher.name}: {result.reason}")
        return MatcherResult(
            "registry",
            False,
            last_state="unknown",
            reason="; ".join(failures),
            transcript_excerpt=_redacted_excerpt(screen),
        )

    def _add(self, matcher: DeclarativeMatcher) -> None:
        if matcher.name in self._matchers:
            raise ValueError(f"duplicate matcher name: {matcher.name}")
        self._matchers[matcher.name] = matcher


def validate_declarative_matcher(definition: Dict[str, object]) -> List[str]:
    errors: List[str] = []
    if not isinstance(definition.get("name"), str) or not str(definition.get("name")).strip():
        errors.append("name is required")
    for key in [
        "menu_prompt_patterns",
        "target_prompt_patterns",
        "host_candidate_patterns",
        "account_prompt_patterns",
        "shell_prompt_patterns",
    ]:
        value = definition.get(key, [])
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"{key} must be a list")
            continue
        if any(not isinstance(item, str) for item in value):
            errors.append(f"{key} must contain only strings")
    if definition.get("menu_prompt_patterns") and not isinstance(definition.get("menu_action_value"), str):
        errors.append("menu_action_value must be a string when menu_prompt_patterns is set")
    return errors


def _load_matchers(search_paths: Iterable[str]) -> List[DeclarativeMatcher]:
    matchers: List[DeclarativeMatcher] = []
    for raw_path in search_paths:
        path = Path(raw_path).expanduser()
        files = sorted(path.glob("*.json")) if path.is_dir() else [path]
        for file_path in files:
            if not file_path.exists() or file_path.suffix.lower() != ".json":
                continue
            with file_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            matchers.append(DeclarativeMatcher(payload, source=str(file_path)))
    return matchers


def _load_packaged_reference_matchers() -> List[DeclarativeMatcher]:
    matchers: List[DeclarativeMatcher] = []
    root = files("ssh_assist_mcp") / "resources/matchers/reference"
    for resource in root.iterdir():
        if resource.name.endswith(".json"):
            payload = json.loads(resource.read_text(encoding="utf-8"))
            matchers.append(DeclarativeMatcher(payload, source=f"package:{resource.name}"))
    return matchers


def _matches_any(patterns: List[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _redacted_excerpt(value: str, limit: int = 800) -> str:
    text = re.sub(r"(?i)(password|token|secret|key)\s*[:=]\s*\S+", r"\1=<redacted>", value)
    text = text.replace("\r", "")
    return text[:limit]

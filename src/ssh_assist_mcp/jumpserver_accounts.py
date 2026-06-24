"""JumpServer account table parsing and account selection helpers."""

from __future__ import annotations

import re
from typing import Dict, List

from .config import GatewayConfig
from .errors import ToolExecutionError


def _parse_account_options(text: str) -> List[Dict[str, str]]:
    accounts: List[Dict[str, str]] = []
    for line in _strip_ansi(text).replace("\r", "").splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            continue
        account_id, name, username = parts[:3]
        if not account_id.isdigit():
            continue
        accounts.append({"id": account_id, "name": name, "username": username})
    return accounts


def _select_account_id(config: GatewayConfig, host: str, account_table: str) -> str:
    host_overrides = config.account_id_by_host or {}
    if host in host_overrides:
        return str(host_overrides[host])

    accounts = _parse_account_options(account_table)
    preferred = (config.preferred_account or "").strip()
    if preferred:
        for account in accounts:
            if _account_matches(account, preferred):
                return account["id"]
        available = ", ".join(
            f"{account['id']}:{account['name']} ({account['username']})" for account in accounts
        ) or "none"
        raise ToolExecutionError(
            f"Gateway {config.name} could not find preferred account {preferred!r} for host {host}. "
            f"Available accounts: {available}."
        )

    if len(accounts) == 1:
        return accounts[0]["id"]

    available = ", ".join(f"{account['id']}:{account['name']} ({account['username']})" for account in accounts) or "none"
    raise ToolExecutionError(
        f"Gateway {config.name} requested an asset account for host {host}, but no preferred_account "
        f"or account_id_by_host matched. Available accounts: {available}."
    )


def _account_matches(account: Dict[str, str], preferred: str) -> bool:
    name = account.get("name", "")
    username = account.get("username", "")
    base_name = re.sub(r"\s*\(.*\)\s*$", "", name).strip()
    return preferred in {name, base_name, username}


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07", "", value)

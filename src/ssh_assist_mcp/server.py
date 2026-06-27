"""MCP-facing tool registry for standalone SSH execution."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Optional

from .config import DEFAULT_COMMAND_TIMEOUT, load_ssh_config
from .matchers import MatcherContext, MatcherRegistry, MatcherResult, validate_declarative_matcher
from .ssh import SSHTool

TOOL_DESCRIPTIONS = {
    "ssh.run_command": (
        "Run one shell command on a remote host through direct SSH or a configured JumpServer-style gateway. "
        "Use confirmed=true only after reviewing risk for destructive commands, state changes, or broad scans."
    ),
    "ssh.run_script": (
        "Run shell or Python script content on a remote host through direct SSH or a configured JumpServer-style gateway. "
        "Scripts require confirmed=true by default because they can perform multiple operations."
    ),
    "ssh.rsync_upload": "Upload a local file or directory to a remote host with rsync over direct SSH.",
    "ssh.rsync_download": "Download a remote file or directory with rsync over direct SSH.",
    "ssh.file_push": (
        "Push one local file to a remote host through direct SSH or a JumpServer gateway without requiring rsync. "
        "Uses base64 chunks with SHA256 verification and is intended for files up to 50MB."
    ),
    "ssh.file_pull": (
        "Pull one remote file to the local machine through direct SSH or a JumpServer gateway without requiring rsync. "
        "Uses base64 with SHA256 verification and is intended for files up to 50MB."
    ),
    "ssh.matcher_list": "List available JumpServer entry matcher plugins from built-ins and configured search paths.",
    "ssh.matcher_validate": "Validate a declarative JumpServer matcher plugin file or JSON definition.",
    "ssh.matcher_probe": "Probe a JumpServer gateway matcher until target shell is reached without executing a remote command.",
    "ssh.matcher_test_transcript": "Replay one JumpServer transcript screen against matcher plugins without opening SSH.",
}

MATCHER_RESOURCE_URIS = {
    "jumpserver-ssh-mcp://docs/matchers/guide": "docs/matchers/guide.md",
    "jumpserver-ssh-mcp://docs/matchers/example": "docs/matchers/example.json",
    "jumpserver-ssh-mcp://docs/matchers/schema": "docs/matchers/schema.json",
    "jumpserver-ssh-mcp://docs/matchers/troubleshooting": "docs/matchers/troubleshooting.md",
    "ssh-assist://docs/matchers/guide": "docs/matchers/guide.md",
    "ssh-assist://docs/matchers/example": "docs/matchers/example.json",
    "ssh-assist://docs/matchers/schema": "docs/matchers/schema.json",
    "ssh-assist://docs/matchers/troubleshooting": "docs/matchers/troubleshooting.md",
}


def _tool() -> SSHTool:
    return SSHTool(load_ssh_config())


def ssh_run_command(
    host: str,
    command: str,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    cwd: Optional[str] = None,
    sudo: bool = False,
    confirmed: bool = False,
    connection_mode: str = "direct",
    gateway: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict:
    return _tool().run_command(
        host,
        command,
        timeout=timeout,
        cwd=cwd,
        sudo=sudo,
        confirmed=confirmed,
        connection_mode=connection_mode,
        gateway=gateway,
        owner_id=owner_id,
    ).to_dict()


def ssh_run_script(
    host: str,
    script_type: str,
    content: str,
    args: Optional[list] = None,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    sudo: bool = False,
    confirmed: bool = False,
    connection_mode: str = "direct",
    gateway: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict:
    return _tool().run_script(
        host,
        script_type,
        content,
        args=args,
        timeout=timeout,
        sudo=sudo,
        confirmed=confirmed,
        connection_mode=connection_mode,
        gateway=gateway,
        owner_id=owner_id,
    ).to_dict()


def ssh_rsync_upload(
    host: str,
    local_path: str,
    remote_path: str,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    confirmed: bool = False,
    connection_mode: str = "direct",
    gateway: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict:
    return _tool().rsync_upload(
        host,
        local_path,
        remote_path,
        timeout=timeout,
        confirmed=confirmed,
        connection_mode=connection_mode,
        gateway=gateway,
        owner_id=owner_id,
    ).to_dict()


def ssh_rsync_download(
    host: str,
    remote_path: str,
    local_path: str,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    confirmed: bool = False,
    connection_mode: str = "direct",
    gateway: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict:
    return _tool().rsync_download(
        host,
        remote_path,
        local_path,
        timeout=timeout,
        confirmed=confirmed,
        connection_mode=connection_mode,
        gateway=gateway,
        owner_id=owner_id,
    ).to_dict()


def ssh_file_push(
    host: str,
    local_path: str,
    remote_path: str,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    confirmed: bool = False,
    connection_mode: str = "direct",
    gateway: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict:
    return _tool().file_push(
        host,
        local_path,
        remote_path,
        timeout=timeout,
        confirmed=confirmed,
        connection_mode=connection_mode,
        gateway=gateway,
        owner_id=owner_id,
    )


def ssh_file_pull(
    host: str,
    remote_path: str,
    local_path: str,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    confirmed: bool = False,
    connection_mode: str = "direct",
    gateway: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> dict:
    return _tool().file_pull(
        host,
        remote_path,
        local_path,
        timeout=timeout,
        confirmed=confirmed,
        connection_mode=connection_mode,
        gateway=gateway,
        owner_id=owner_id,
    )


def ssh_matcher_list(profile_path: Optional[str] = None) -> dict:
    config = load_ssh_config(profile_path)
    registry = MatcherRegistry(search_paths=config.matcher_search_paths or [])
    gateways = {}
    for name, gateway in (config.gateways or {}).items():
        gateways[name] = {
            "matcher": gateway.matcher.name if gateway.matcher else None,
            "command": gateway.command,
        }
    return {
        "matchers": registry.list(),
        "default_gateway": config.default_gateway,
        "gateways": gateways,
    }


def ssh_matcher_validate(path: Optional[str] = None, definition: Optional[dict] = None) -> dict:
    if path:
        matcher_path = Path(path).expanduser()
        with matcher_path.open("r", encoding="utf-8") as handle:
            definition = json.load(handle)
    if definition is None:
        return {"valid": False, "errors": ["path or definition is required"]}
    errors = validate_declarative_matcher(definition)
    return {
        "valid": not errors,
        "name": definition.get("name") if isinstance(definition, dict) else None,
        "errors": errors,
    }


def ssh_matcher_probe(host: str, gateway: Optional[str] = None, timeout: int = 60, profile_path: Optional[str] = None) -> dict:
    return SSHTool(load_ssh_config(profile_path)).matcher_probe(host, gateway=gateway, timeout=timeout)


def ssh_matcher_test_transcript(
    transcript: str,
    host: str,
    matcher: Optional[str] = None,
    preferred_account: Optional[str] = None,
    gateway: Optional[str] = None,
    profile_path: Optional[str] = None,
) -> dict:
    config = load_ssh_config(profile_path)
    registry = MatcherRegistry(search_paths=config.matcher_search_paths or [])
    if gateway and not matcher:
        gateway_config = (config.gateways or {}).get(gateway)
        if gateway_config and gateway_config.matcher:
            matcher = gateway_config.matcher.name
        if gateway_config and not preferred_account:
            preferred_account = gateway_config.preferred_account
    result = registry.match(
        transcript,
        MatcherContext(host=host, preferred_account=preferred_account, gateway=gateway),
        matcher_name=matcher,
    )
    return _matcher_result_to_dict(result)


def matcher_guide_resource() -> str:
    return _read_doc_resource("jumpserver-ssh-mcp://docs/matchers/guide")


def matcher_example_resource() -> str:
    return _read_doc_resource("jumpserver-ssh-mcp://docs/matchers/example")


def matcher_schema_resource() -> str:
    return _read_doc_resource("jumpserver-ssh-mcp://docs/matchers/schema")


def matcher_troubleshooting_resource() -> str:
    return _read_doc_resource("jumpserver-ssh-mcp://docs/matchers/troubleshooting")


def _matcher_result_to_dict(result: MatcherResult) -> dict:
    return {
        "matcher": result.matcher,
        "matched": result.matched,
        "last_state": result.last_state,
        "reason": result.reason,
        "transcript_excerpt": result.transcript_excerpt,
        "action": None
        if result.action is None
        else {
            "type": result.action.type,
            "value": result.action.value,
        },
    }


def _read_doc_resource(uri: str) -> str:
    repo_path = Path(__file__).resolve().parents[2] / MATCHER_RESOURCE_URIS[uri]
    if repo_path.exists():
        return repo_path.read_text(encoding="utf-8")
    package_path = files("ssh_assist_mcp") / f"resources/{MATCHER_RESOURCE_URIS[uri]}"
    return package_path.read_text(encoding="utf-8")


def register_tools(mcp) -> None:
    mcp.tool(name="ssh.run_command", description=TOOL_DESCRIPTIONS["ssh.run_command"])(ssh_run_command)
    mcp.tool(name="ssh.run_script", description=TOOL_DESCRIPTIONS["ssh.run_script"])(ssh_run_script)
    mcp.tool(name="ssh.rsync_upload", description=TOOL_DESCRIPTIONS["ssh.rsync_upload"])(ssh_rsync_upload)
    mcp.tool(name="ssh.rsync_download", description=TOOL_DESCRIPTIONS["ssh.rsync_download"])(ssh_rsync_download)
    mcp.tool(name="ssh.file_push", description=TOOL_DESCRIPTIONS["ssh.file_push"])(ssh_file_push)
    mcp.tool(name="ssh.file_pull", description=TOOL_DESCRIPTIONS["ssh.file_pull"])(ssh_file_pull)
    mcp.tool(name="ssh.matcher_list", description=TOOL_DESCRIPTIONS["ssh.matcher_list"])(ssh_matcher_list)
    mcp.tool(name="ssh.matcher_validate", description=TOOL_DESCRIPTIONS["ssh.matcher_validate"])(ssh_matcher_validate)
    mcp.tool(name="ssh.matcher_probe", description=TOOL_DESCRIPTIONS["ssh.matcher_probe"])(ssh_matcher_probe)
    mcp.tool(name="ssh.matcher_test_transcript", description=TOOL_DESCRIPTIONS["ssh.matcher_test_transcript"])(
        ssh_matcher_test_transcript
    )


def register_resources(mcp) -> None:
    for uri, handler in (
        ("jumpserver-ssh-mcp://docs/matchers/guide", matcher_guide_resource),
        ("jumpserver-ssh-mcp://docs/matchers/example", matcher_example_resource),
        ("jumpserver-ssh-mcp://docs/matchers/schema", matcher_schema_resource),
        ("jumpserver-ssh-mcp://docs/matchers/troubleshooting", matcher_troubleshooting_resource),
        ("ssh-assist://docs/matchers/guide", matcher_guide_resource),
        ("ssh-assist://docs/matchers/example", matcher_example_resource),
        ("ssh-assist://docs/matchers/schema", matcher_schema_resource),
        ("ssh-assist://docs/matchers/troubleshooting", matcher_troubleshooting_resource),
    ):
        mcp.resource(uri)(handler)


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install jumpserver-ssh-mcp[mcp] to run the MCP server.") from exc
    mcp = FastMCP("jumpserver-ssh-mcp")
    register_tools(mcp)
    register_resources(mcp)
    mcp.run()


if __name__ == "__main__":
    main()

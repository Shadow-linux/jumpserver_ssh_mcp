"""Command line interface for ssh-assist-mcp."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import SafetyError, ToolExecutionError
from .ssh import SSHTool, load_ssh_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ssh-assist")
    parser.add_argument("--profile", help="Path to ssh-assist YAML profile.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("host")
    parent.add_argument("--timeout", type=int, default=30)
    parent.add_argument("--connection-mode", choices=["direct", "gateway"], default="direct")
    parent.add_argument("--gateway")

    run = subparsers.add_parser("run", parents=[parent], help="Run one remote command.")
    run.add_argument("--command", required=True, dest="remote_command")
    run.add_argument("--cwd")
    run.add_argument("--sudo", action="store_true")
    run.add_argument("--confirm-risk", action="store_true")

    script = subparsers.add_parser("script", parents=[parent], help="Run a remote shell/python script.")
    script.add_argument("--type", choices=["shell", "python"], default="shell")
    script.add_argument("--content")
    script.add_argument("--file")
    script.add_argument("--arg", action="append", default=[])
    script.add_argument("--sudo", action="store_true")
    script.add_argument("--confirm-risk", action="store_true")

    upload = subparsers.add_parser("upload", parents=[parent], help="Upload a file or directory with rsync.")
    upload.add_argument("--local", required=True)
    upload.add_argument("--remote", required=True)
    upload.add_argument("--confirm-risk", action="store_true")

    download = subparsers.add_parser("download", parents=[parent], help="Download a file or directory with rsync.")
    download.add_argument("--remote", required=True)
    download.add_argument("--local", required=True)
    download.add_argument("--confirm-risk", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    tool = SSHTool(load_ssh_config(args.profile))
    try:
        if args.command == "run":
            result = tool.run_command(
                args.host,
                args.remote_command,
                timeout=args.timeout,
                cwd=args.cwd,
                sudo=args.sudo,
                confirmed=args.confirm_risk,
                connection_mode=args.connection_mode,
                gateway=args.gateway,
            )
        elif args.command == "script":
            result = tool.run_script(
                args.host,
                args.type,
                _script_content(args),
                args=args.arg,
                timeout=args.timeout,
                sudo=args.sudo,
                confirmed=args.confirm_risk,
                connection_mode=args.connection_mode,
                gateway=args.gateway,
            )
        elif args.command == "upload":
            result = tool.rsync_upload(
                args.host,
                args.local,
                args.remote,
                timeout=args.timeout,
                confirmed=args.confirm_risk,
                connection_mode=args.connection_mode,
                gateway=args.gateway,
            )
        elif args.command == "download":
            result = tool.rsync_download(
                args.host,
                args.remote,
                args.local,
                timeout=args.timeout,
                confirmed=args.confirm_risk,
                connection_mode=args.connection_mode,
                gateway=args.gateway,
            )
        else:
            parser.error(f"Unknown command: {args.command}")
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return result.returncode
    except (SafetyError, ToolExecutionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


def _script_content(args) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.content is not None:
        return args.content
    raise ToolExecutionError("script requires --content or --file.")


if __name__ == "__main__":
    raise SystemExit(main())

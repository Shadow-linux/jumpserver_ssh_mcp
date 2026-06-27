import json
import os
import signal
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ssh_assist_mcp.config import DEFAULT_COMMAND_TIMEOUT
from ssh_assist_mcp.result import CommandResult
from ssh_assist_mcp.server import ssh_run_command
from ssh_assist_mcp.sessions import DEFAULT_OWNER_CLEANUP_GRACE_SECONDS, GatewaySessionRegistry


class OwnerSessionCleanupTest(unittest.TestCase):
    def test_default_cleanup_grace_is_three_minutes(self):
        self.assertEqual(DEFAULT_OWNER_CLEANUP_GRACE_SECONDS, 180)

    def test_cleanup_kills_only_stale_sessions_for_same_owner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = GatewaySessionRegistry(Path(temp_dir))
            registry.write(
                owner_id="agent-a",
                child_pid=111,
                mcp_pid=os.getpid(),
                gateway="gw",
                target="10.0.0.1",
                command_sha256="aaa",
                started_at=100.0,
            )
            registry.write(
                owner_id="agent-b",
                child_pid=222,
                mcp_pid=os.getpid(),
                gateway="gw",
                target="10.0.0.2",
                command_sha256="bbb",
                started_at=100.0,
            )

            with patch("ssh_assist_mcp.sessions._pid_exists", return_value=True), patch(
                "ssh_assist_mcp.sessions.os.kill"
            ) as kill:
                removed = registry.cleanup_owner("agent-a", stale_after_seconds=10, now=200.0)

            self.assertEqual(removed, [111])
            kill.assert_called_once_with(111, signal.SIGTERM)
            self.assertFalse((Path(temp_dir) / "agent-a" / "111.json").exists())
            self.assertTrue((Path(temp_dir) / "agent-b" / "222.json").exists())

    def test_cleanup_ignores_recent_same_owner_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = GatewaySessionRegistry(Path(temp_dir))
            registry.write(
                owner_id="agent-a",
                child_pid=111,
                mcp_pid=os.getpid(),
                gateway="gw",
                target="10.0.0.1",
                command_sha256="aaa",
                started_at=195.0,
            )

            with patch("ssh_assist_mcp.sessions._pid_exists", return_value=True), patch(
                "ssh_assist_mcp.sessions.os.kill"
            ) as kill:
                removed = registry.cleanup_owner("agent-a", stale_after_seconds=10, now=200.0)

            self.assertEqual(removed, [])
            kill.assert_not_called()
            self.assertTrue((Path(temp_dir) / "agent-a" / "111.json").exists())

    def test_cleanup_removes_empty_owner_directory_after_stale_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = GatewaySessionRegistry(Path(temp_dir))
            registry.write(
                owner_id="agent-a",
                child_pid=111,
                mcp_pid=os.getpid(),
                gateway="gw",
                target="10.0.0.1",
                command_sha256="aaa",
                started_at=100.0,
            )

            with patch("ssh_assist_mcp.sessions._pid_exists", return_value=False):
                registry.cleanup_owner("agent-a", stale_after_seconds=10, now=200.0)

            self.assertFalse((Path(temp_dir) / "agent-a").exists())

    def test_remove_deletes_empty_owner_directory_after_session_finishes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = GatewaySessionRegistry(Path(temp_dir))
            registry.write(
                owner_id="agent-a",
                child_pid=111,
                mcp_pid=os.getpid(),
                gateway="gw",
                target="10.0.0.1",
                command_sha256="aaa",
                started_at=100.0,
            )

            registry.remove("agent-a", 111)

            self.assertFalse((Path(temp_dir) / "agent-a").exists())

    def test_session_metadata_is_redacted_to_hash_not_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = GatewaySessionRegistry(Path(temp_dir))
            path = registry.write(
                owner_id="agent/a",
                child_pid=111,
                mcp_pid=222,
                gateway="gw",
                target="10.0.0.1",
                command_sha256="abc123",
                started_at=100.0,
            )

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["owner_id"], "agent/a")
            self.assertEqual(payload["command_sha256"], "abc123")
            self.assertNotIn("command", payload)
            self.assertEqual(path.parent.name, "agent-a")

    def test_server_run_command_forwards_owner_id(self):
        expected = CommandResult(["ssh"], 0, "ok\n", "")
        with patch("ssh_assist_mcp.server.SSHTool.run_command", return_value=expected) as run:
            self.assertEqual(ssh_run_command("10.0.0.1", "uptime", owner_id="agent-a")["stdout"], "ok\n")

        run.assert_called_once_with(
            "10.0.0.1",
            "uptime",
            timeout=DEFAULT_COMMAND_TIMEOUT,
            cwd=None,
            sudo=False,
            confirmed=False,
            connection_mode="direct",
            gateway=None,
            owner_id="agent-a",
        )


if __name__ == "__main__":
    unittest.main()

import subprocess
import unittest
from unittest.mock import patch

from ssh_assist_mcp.config import DEFAULT_COMMAND_TIMEOUT, GatewayConfig, SSHConfig
from ssh_assist_mcp.gateway import GatewaySSHRunner
from ssh_assist_mcp.result import CommandResult
from ssh_assist_mcp.server import ssh_run_command
from ssh_assist_mcp.ssh import SSHTool


class TimeoutBehaviorTest(unittest.TestCase):
    def test_direct_command_timeout_returns_result(self):
        tool = SSHTool(SSHConfig())

        with patch("ssh_assist_mcp.ssh.subprocess.run") as run:
            run.side_effect = subprocess.TimeoutExpired(
                cmd=["ssh", "example", "sleep 999"],
                timeout=DEFAULT_COMMAND_TIMEOUT,
                output="partial\n",
                stderr="still running\n",
            )

            result = tool.run_command("example", "sleep 999")

        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.stdout, "partial\n")
        self.assertIn(f"timed out after {DEFAULT_COMMAND_TIMEOUT} seconds", result.stderr)
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["timeout"], DEFAULT_COMMAND_TIMEOUT)

    def test_gateway_command_timeout_returns_result(self):
        runner = GatewaySSHRunner(
            GatewayConfig(
                name="demo",
                type="interactive_expect",
                command="ssh jump",
                target_prompt_patterns=[],
                shell_prompt_patterns=[],
                max_attempts=2,
            )
        )

        with patch.object(runner, "_run_once", side_effect=TimeoutError("command timed out")):
            result = runner.run_command("10.0.0.1", "sleep 999", DEFAULT_COMMAND_TIMEOUT, None, lambda *args, **kwargs: None)

        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.stdout, "")
        self.assertIn(f"timed out after {DEFAULT_COMMAND_TIMEOUT} seconds", result.stderr)

    def test_server_run_command_default_timeout_is_1800(self):
        expected = CommandResult(["ssh"], 0, "ok\n", "")
        with patch("ssh_assist_mcp.server.SSHTool.run_command", return_value=expected) as run:
            self.assertEqual(ssh_run_command("10.0.0.1", "uptime")["stdout"], "ok\n")

        run.assert_called_once_with(
            "10.0.0.1",
            "uptime",
            timeout=DEFAULT_COMMAND_TIMEOUT,
            cwd=None,
            sudo=False,
            confirmed=False,
            connection_mode="direct",
            gateway=None,
            owner_id=None,
        )


if __name__ == "__main__":
    unittest.main()

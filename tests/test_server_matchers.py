import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ssh_assist_mcp.server import (
    MATCHER_RESOURCE_URIS,
    register_resources,
    register_tools,
    ssh_matcher_list,
    ssh_matcher_probe,
    ssh_matcher_test_transcript,
    ssh_matcher_validate,
    ssh_file_pull,
    ssh_file_push,
)


class FakeMCP:
    def __init__(self):
        self.tools = {}
        self.resources = {}

    def tool(self, name, description):
        def decorator(func):
            self.tools[name] = {"description": description, "func": func}
            return func

        return decorator

    def resource(self, uri):
        def decorator(func):
            self.resources[uri] = func
            return func

        return decorator


class ServerMatcherToolsTest(unittest.TestCase):
    def test_matcher_resources_are_declared(self):
        self.assertIn("jumpserver-ssh-mcp://docs/matchers/guide", MATCHER_RESOURCE_URIS)
        self.assertIn("jumpserver-ssh-mcp://docs/matchers/schema", MATCHER_RESOURCE_URIS)
        self.assertIn("ssh-assist://docs/matchers/guide", MATCHER_RESOURCE_URIS)
        self.assertIn("ssh-assist://docs/matchers/schema", MATCHER_RESOURCE_URIS)

    def test_matcher_list_returns_builtin(self):
        result = ssh_matcher_list()

        self.assertIn("builtin-generic", result["matchers"])

    def test_registers_mcp_tools_and_resource_aliases(self):
        fake = FakeMCP()

        register_tools(fake)
        register_resources(fake)

        self.assertIn("ssh.run_command", fake.tools)
        self.assertIn("ssh.file_push", fake.tools)
        self.assertIn("ssh.file_pull", fake.tools)
        self.assertIn("ssh.matcher_list", fake.tools)
        self.assertIn("ssh.matcher_probe", fake.tools)
        self.assertIn("jumpserver-ssh-mcp://docs/matchers/guide", fake.resources)
        self.assertIn("ssh-assist://docs/matchers/guide", fake.resources)

    def test_matcher_validate_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "demo.json"
            path.write_text(json.dumps({"name": "demo"}), encoding="utf-8")

            result = ssh_matcher_validate(path=str(path))

        self.assertTrue(result["valid"])
        self.assertEqual(result["name"], "demo")

    def test_matcher_test_transcript_uses_requested_matcher(self):
        result = ssh_matcher_test_transcript(
            transcript="请输入资产 IP:",
            host="10.1.1.1",
            matcher="builtin-generic",
        )

        self.assertTrue(result["matched"])
        self.assertEqual(result["action"]["type"], "send_text")
        self.assertEqual(result["action"]["value"], "10.1.1.1")

    def test_matcher_probe_calls_tool_without_remote_command(self):
        expected = {"gateway": "demo", "host": "10.1.1.1", "shell_reached": True, "steps": []}
        with patch("ssh_assist_mcp.server.SSHTool.matcher_probe", return_value=expected) as probe:
            result = ssh_matcher_probe(host="10.1.1.1", gateway="demo", timeout=10)

        probe.assert_called_once_with("10.1.1.1", gateway="demo", timeout=10)
        self.assertEqual(result, expected)

    def test_file_transfer_tools_call_tool(self):
        with patch("ssh_assist_mcp.server.SSHTool.file_push", return_value={"direction": "push"}) as push:
            self.assertEqual(
                ssh_file_push("10.0.0.1", "/local.txt", "/remote.txt", connection_mode="gateway", gateway="demo"),
                {"direction": "push"},
            )
        push.assert_called_once_with(
            "10.0.0.1",
            "/local.txt",
            "/remote.txt",
            timeout=300,
            confirmed=False,
            connection_mode="gateway",
            gateway="demo",
        )

        with patch("ssh_assist_mcp.server.SSHTool.file_pull", return_value={"direction": "pull"}) as pull:
            self.assertEqual(
                ssh_file_pull("10.0.0.1", "/remote.txt", "/local.txt", connection_mode="gateway", gateway="demo"),
                {"direction": "pull"},
            )
        pull.assert_called_once_with(
            "10.0.0.1",
            "/remote.txt",
            "/local.txt",
            timeout=300,
            confirmed=False,
            connection_mode="gateway",
            gateway="demo",
        )


if __name__ == "__main__":
    unittest.main()

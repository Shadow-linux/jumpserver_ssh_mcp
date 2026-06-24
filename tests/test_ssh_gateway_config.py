import unittest
import json
import tempfile
from pathlib import Path

from ssh_assist_mcp.config import GatewayConfig, SSHConfig
from ssh_assist_mcp.errors import ToolExecutionError
from ssh_assist_mcp.ssh import SSHTool


class SSHGatewayConfigTest(unittest.TestCase):
    def test_uses_default_gateway_when_gateway_not_supplied(self):
        config = SSHConfig(
            gateways={
                "default": GatewayConfig(
                    name="default",
                    type="interactive_expect",
                    command="ssh jump",
                    target_prompt_patterns=[],
                    shell_prompt_patterns=[],
                )
            },
            default_gateway="default",
        )

        gateway = SSHTool(config)._gateway_config(None)

        self.assertEqual(gateway.name, "default")

    def test_requires_gateway_when_no_default_exists(self):
        with self.assertRaises(ToolExecutionError) as ctx:
            SSHTool(SSHConfig(gateways={}))._gateway_config(None)

        self.assertIn("gateway is required", str(ctx.exception))

    def test_builds_matcher_registry_from_config_search_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "demo.json"
            path.write_text(json.dumps({"name": "demo"}), encoding="utf-8")
            tool = SSHTool(SSHConfig(matcher_search_paths=[temp_dir]))

            registry = tool._matcher_registry()

        self.assertIn("demo", registry.list())


if __name__ == "__main__":
    unittest.main()

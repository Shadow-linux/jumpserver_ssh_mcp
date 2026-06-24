import unittest
from pathlib import Path

from ssh_assist_mcp.config import SSHConfig, load_ssh_config


class SSHConfigTest(unittest.TestCase):
    def test_parses_default_gateway_and_matcher_search_paths(self):
        config = SSHConfig.from_profile(
            {
                "ssh": {
                    "default_gateway": "ttyuyin-test",
                    "defaults": {"user": "ops", "port": 22, "strict_host_key_checking": "no"},
                    "gateways": {
                        "ttyuyin-test": {
                            "command": "ssh jump-test",
                            "matcher": "ttyuyin-generic",
                        },
                        "qmzy": {
                            "command": "ssh qmzy",
                            "matcher": {"name": "qmzy-reference", "path": "./matchers/custom/qmzy.yaml"},
                        },
                    },
                },
                "matchers": {
                    "search_paths": ["./matchers/custom", "/Users/example/.config/jumpserver-ssh-mcp/matchers"]
                },
            }
        )

        self.assertEqual(config.default_gateway, "ttyuyin-test")
        self.assertEqual(config.user, "ops")
        self.assertEqual(config.matcher_search_paths, ["./matchers/custom", "/Users/example/.config/jumpserver-ssh-mcp/matchers"])
        self.assertEqual(config.gateways["ttyuyin-test"].matcher.name, "ttyuyin-generic")
        self.assertIsNone(config.gateways["ttyuyin-test"].matcher.path)
        self.assertEqual(config.gateways["qmzy"].matcher.name, "qmzy-reference")
        self.assertEqual(config.gateways["qmzy"].matcher.path, "./matchers/custom/qmzy.yaml")

    def test_parses_simple_product_profile(self):
        config = SSHConfig.from_profile(
            {
                "default_gateway": "pro-jumpserver",
                "gateways": {
                    "pro-jumpserver": {
                        "command": "ssh -i ~/.ssh/pro.pem ops@jump.example.com -p2222",
                        "matcher": "builtin-generic",
                        "preferred_account": "__su",
                    }
                },
                "matchers": {
                    "custom_dirs": ["~/.config/jumpserver-ssh-mcp/matchers"],
                },
            }
        )

        gateway = config.gateways["pro-jumpserver"]
        self.assertEqual(config.default_gateway, "pro-jumpserver")
        self.assertEqual(gateway.command, "ssh -i ~/.ssh/pro.pem ops@jump.example.com -p2222")
        self.assertEqual(gateway.type, "interactive_expect")
        self.assertEqual(gateway.matcher.name, "builtin-generic")
        self.assertEqual(gateway.preferred_account, "__su")
        self.assertEqual(config.matcher_search_paths, ["~/.config/jumpserver-ssh-mcp/matchers"])

    def test_simple_profile_defaults_matcher_to_builtin_generic(self):
        config = SSHConfig.from_profile(
            {
                "gateways": {
                    "test-jumpserver": {
                        "command": "ssh ops@jump-test.example.com -p2222",
                    }
                }
            }
        )

        self.assertEqual(config.gateways["test-jumpserver"].matcher.name, "builtin-generic")

    def test_missing_profile_sections_use_safe_defaults(self):
        config = SSHConfig.from_profile({})

        self.assertIsNone(config.default_gateway)
        self.assertEqual(config.matcher_search_paths, [])
        self.assertEqual(config.gateways, {})

    def test_example_profile_is_loadable(self):
        profile_path = Path(__file__).resolve().parents[1] / "config/example.yaml"

        config = load_ssh_config(str(profile_path))

        self.assertEqual(config.default_gateway, "jumpserver-test")
        self.assertIn("jumpserver-test", config.gateways)
        self.assertEqual(config.gateways["jumpserver-test"].matcher.name, "builtin-generic")
        self.assertIn("matchers/custom", config.matcher_search_paths)

    def test_full_example_profile_is_loadable(self):
        profile_path = Path(__file__).resolve().parents[1] / "config/full-example.yaml"

        config = load_ssh_config(str(profile_path))

        gateway = config.gateways["jumpserver-test"]
        self.assertEqual(config.default_gateway, "jumpserver-test")
        self.assertEqual(gateway.type, "interactive_expect")
        self.assertEqual(gateway.matcher.name, "builtin-generic")
        self.assertEqual(gateway.preferred_account, "__su")
        self.assertEqual(gateway.account_id_by_host["10.0.0.10"], "2")
        self.assertIsNotNone(gateway.privilege_escalation)


if __name__ == "__main__":
    unittest.main()

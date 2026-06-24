import unittest
from contextlib import contextmanager
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ssh_assist_mcp.config import SSHConfig, load_ssh_config


@contextmanager
def temporary_cwd(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


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
                            "matcher": {"name": "qmzy-reference", "path": "~/jumpserver-ssh-mcp/matchers/qmzy.yaml"},
                        },
                    },
                },
                "matchers": {
                    "search_paths": ["~/jumpserver-ssh-mcp/matchers"]
                },
            }
        )

        self.assertEqual(config.default_gateway, "ttyuyin-test")
        self.assertEqual(config.user, "ops")
        self.assertEqual(config.matcher_search_paths, ["~/jumpserver-ssh-mcp/matchers"])
        self.assertEqual(config.gateways["ttyuyin-test"].matcher.name, "ttyuyin-generic")
        self.assertIsNone(config.gateways["ttyuyin-test"].matcher.path)
        self.assertEqual(config.gateways["qmzy"].matcher.name, "qmzy-reference")
        self.assertEqual(config.gateways["qmzy"].matcher.path, "~/jumpserver-ssh-mcp/matchers/qmzy.yaml")

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
                    "custom_dirs": ["~/jumpserver-ssh-mcp/matchers"],
                },
            }
        )

        gateway = config.gateways["pro-jumpserver"]
        self.assertEqual(config.default_gateway, "pro-jumpserver")
        self.assertEqual(gateway.command, "ssh -i ~/.ssh/pro.pem ops@jump.example.com -p2222")
        self.assertEqual(gateway.type, "interactive_expect")
        self.assertEqual(gateway.matcher.name, "builtin-generic")
        self.assertEqual(gateway.preferred_account, "__su")
        self.assertEqual(config.matcher_search_paths, ["~/jumpserver-ssh-mcp/matchers"])

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

    def test_default_profile_comes_from_user_runtime_directory(self):
        with TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "jumpserver-ssh-mcp" / "config" / "local.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                """
default_gateway: user-runtime
gateways:
  user-runtime:
    command: ssh ops@jump.example.com -p2222
matchers:
  custom_dirs:
    - ~/jumpserver-ssh-mcp/matchers
""".lstrip(),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True), patch("ssh_assist_mcp.paths.Path.home", return_value=Path(temp_dir)):
                config = load_ssh_config()

        self.assertEqual(config.default_gateway, "user-runtime")
        self.assertIn("user-runtime", config.gateways)
        self.assertEqual(config.matcher_search_paths, ["~/jumpserver-ssh-mcp/matchers"])

    def test_default_profile_falls_back_to_legacy_local_profile(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path = root / "config" / "local.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                """
default_gateway: legacy-local
gateways:
  legacy-local:
    command: ssh ops@legacy.example.com -p2222
""".lstrip(),
                encoding="utf-8",
            )

            with temporary_cwd(root), patch.dict("os.environ", {}, clear=True), patch(
                "ssh_assist_mcp.paths.Path.home", return_value=root / "home"
            ):
                config = load_ssh_config()

        self.assertEqual(config.default_gateway, "legacy-local")
        self.assertIn("legacy-local", config.gateways)

    def test_default_profile_falls_back_to_example_profile_for_smoke(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path = root / "config" / "example.yaml"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                """
default_gateway: example-smoke
gateways:
  example-smoke:
    command: ssh ops@example.invalid -p2222
""".lstrip(),
                encoding="utf-8",
            )

            with temporary_cwd(root), patch.dict("os.environ", {}, clear=True), patch(
                "ssh_assist_mcp.paths.Path.home", return_value=root / "home"
            ):
                config = load_ssh_config()

        self.assertEqual(config.default_gateway, "example-smoke")
        self.assertIn("example-smoke", config.gateways)

    def test_example_profile_is_loadable(self):
        profile_path = Path(__file__).resolve().parents[1] / "config/example.yaml"

        config = load_ssh_config(str(profile_path))

        self.assertEqual(config.default_gateway, "jumpserver-test")
        self.assertIn("jumpserver-test", config.gateways)
        self.assertEqual(config.gateways["jumpserver-test"].matcher.name, "builtin-generic")
        self.assertIn("~/jumpserver-ssh-mcp/matchers", config.matcher_search_paths)

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

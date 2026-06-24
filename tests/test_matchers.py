import json
import tempfile
import unittest
from pathlib import Path

from ssh_assist_mcp.matchers import (
    BuiltinJumpServerMatcher,
    DeclarativeMatcher,
    MatcherContext,
    MatcherRegistry,
    validate_declarative_matcher,
)


ACCOUNT_TABLE = """
  ID    | 名称                                 | 用户名
--------+--------------------------------------+--------------------------------
  1     | __su(ssh key)                        | __su
  2     | wangheng(ssh key)                    | wangheng
提示：输入资产[host(10.211.4.113)]的账号ID
"""


class MatchersTest(unittest.TestCase):
    def test_builtin_matches_chinese_host_prompt(self):
        matcher = BuiltinJumpServerMatcher()

        result = matcher.match("请输入资产 IP 或主机名:", MatcherContext(host="10.211.4.113"))

        self.assertTrue(result.matched)
        self.assertEqual(result.action.type, "send_text")
        self.assertEqual(result.action.value, "10.211.4.113")
        self.assertEqual(result.last_state, "target_prompt")

    def test_builtin_matches_english_host_prompt(self):
        matcher = BuiltinJumpServerMatcher()

        result = matcher.match("Please input host or IP:", MatcherContext(host="app-01"))

        self.assertTrue(result.matched)
        self.assertEqual(result.action.value, "app-01")

    def test_builtin_treats_jumpserver_opt_prompt_as_target_prompt(self):
        matcher = BuiltinJumpServerMatcher()

        result = matcher.match("Opt> ", MatcherContext(host="10.211.4.113"))

        self.assertTrue(result.matched)
        self.assertEqual(result.action.type, "send_text")
        self.assertEqual(result.action.value, "10.211.4.113")
        self.assertEqual(result.last_state, "target_prompt")

    def test_builtin_treats_jumpserver_host_prompt_as_target_prompt(self):
        matcher = BuiltinJumpServerMatcher()

        result = matcher.match("[Host]> ", MatcherContext(host="10.211.4.113"))

        self.assertTrue(result.matched)
        self.assertEqual(result.action.type, "send_text")
        self.assertEqual(result.action.value, "10.211.4.113")
        self.assertEqual(result.last_state, "target_prompt")

    def test_builtin_does_not_send_host_on_jumpserver_menu_help_text(self):
        matcher = BuiltinJumpServerMatcher()
        menu_help = "1) 输入 部分IP，主机名，备注 进行搜索登录(如果唯一)."

        result = matcher.match(menu_help, MatcherContext(host="10.211.4.113"))

        self.assertFalse(result.matched)

    def test_builtin_does_not_send_host_on_english_jumpserver_menu_help_text(self):
        matcher = BuiltinJumpServerMatcher()
        menu_help = "1) Enter part IP, Hostname, Comment to to search login if unique."

        result = matcher.match(menu_help, MatcherContext(host="10.2.39.152"))

        self.assertFalse(result.matched)

    def test_builtin_selects_preferred_account(self):
        matcher = BuiltinJumpServerMatcher()

        result = matcher.match(ACCOUNT_TABLE + "\nID> ", MatcherContext(host="10.211.4.113", preferred_account="__su"))

        self.assertTrue(result.matched)
        self.assertEqual(result.action.type, "send_text")
        self.assertEqual(result.action.value, "1")
        self.assertEqual(result.last_state, "account_prompt")

    def test_builtin_waits_for_account_input_prompt_before_selecting(self):
        matcher = BuiltinJumpServerMatcher()

        result = matcher.match(ACCOUNT_TABLE, MatcherContext(host="10.211.4.113", preferred_account="__su"))

        self.assertTrue(result.matched)
        self.assertEqual(result.action.type, "wait")
        self.assertEqual(result.last_state, "account_prompt")

    def test_builtin_account_prompt_with_id_arrow_is_not_shell(self):
        matcher = BuiltinJumpServerMatcher()
        screen = ACCOUNT_TABLE + "\nID> "

        result = matcher.match(screen, MatcherContext(host="10.211.4.113", preferred_account="__su"))

        self.assertTrue(result.matched)
        self.assertEqual(result.action.type, "send_text")
        self.assertEqual(result.action.value, "1")
        self.assertEqual(result.last_state, "account_prompt")

    def test_builtin_reports_shell_reached(self):
        matcher = BuiltinJumpServerMatcher()

        result = matcher.match("[root@app-01 ~]# ", MatcherContext(host="app-01"))

        self.assertTrue(result.matched)
        self.assertEqual(result.action.type, "shell_reached")

    def test_registry_loads_custom_declarative_matcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "custom.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "custom-demo",
                        "target_prompt_patterns": ["Choose server"],
                        "shell_prompt_patterns": [r"[$#>] "],
                    }
                ),
                encoding="utf-8",
            )

            registry = MatcherRegistry(search_paths=[temp_dir])
            result = registry.get("custom-demo").match("Choose server:", MatcherContext(host="10.1.1.1"))

        self.assertEqual(result.action.type, "send_text")
        self.assertEqual(result.action.value, "10.1.1.1")

    def test_declarative_matcher_can_send_fixed_menu_action_before_target(self):
        matcher = BuiltinJumpServerMatcher()
        custom = {
            "name": "qmzy-reference",
            "menu_prompt_patterns": [r"Opt>\s*$"],
            "menu_action_value": "p",
            "target_prompt_patterns": [r"\[Host\]>\s*$"],
            "shell_prompt_patterns": [r"[$#>]\s*$", r"\w+@[-\w]+:[^\r\n]*$"],
        }
        registry = MatcherRegistry(builtins=[matcher])
        registry._add(DeclarativeMatcher(custom))

        menu_result = registry.get("qmzy-reference").match("Opt> ", MatcherContext(host="2"))
        host_result = registry.get("qmzy-reference").match("[Host]> ", MatcherContext(host="2"))

        self.assertEqual(menu_result.action.type, "send_text")
        self.assertEqual(menu_result.action.value, "p")
        self.assertEqual(menu_result.last_state, "menu_prompt")
        self.assertEqual(host_result.action.value, "2")
        shell_result = registry.get("qmzy-reference").match("root@domain:~", MatcherContext(host="2"))
        self.assertEqual(shell_result.action.type, "shell_reached")

    def test_declarative_target_prompt_wins_over_asset_table_shape(self):
        matcher = DeclarativeMatcher(
            {
                "name": "qmzy-reference",
                "target_prompt_patterns": [r"\[Host\]>\s*$"],
                "shell_prompt_patterns": [r"[$#>]\s*$"],
            }
        )
        screen = "  ID | NAME | ADDRESS\n  2  | domain | 10.2.72.236\n[Host]> "

        result = matcher.match(screen, MatcherContext(host="2"))

        self.assertEqual(result.action.type, "send_text")
        self.assertEqual(result.action.value, "2")
        self.assertEqual(result.last_state, "target_prompt")

    def test_registry_rejects_duplicate_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "builtin-generic.json"
            path.write_text(json.dumps({"name": "builtin-generic"}), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                MatcherRegistry(search_paths=[temp_dir])

        self.assertIn("duplicate matcher", str(ctx.exception))

    def test_validate_declarative_matcher_reports_invalid_payload(self):
        errors = validate_declarative_matcher({"target_prompt_patterns": "bad"})

        self.assertIn("name is required", errors)
        self.assertIn("target_prompt_patterns must be a list", errors)


if __name__ == "__main__":
    unittest.main()

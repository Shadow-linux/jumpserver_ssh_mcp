import unittest

from ssh_assist_mcp.errors import ToolExecutionError
from ssh_assist_mcp.config import GatewayConfig
from ssh_assist_mcp.jumpserver_accounts import (
    _parse_account_options,
    _select_account_id,
)
from ssh_assist_mcp.gateway import _clean_gateway_output
from ssh_assist_mcp.matchers import MatcherRegistry


ACCOUNT_TABLE = """
  ID    | 名称                                 | 用户名
--------+--------------------------------------+--------------------------------
  1     | __su(ssh key)                        | __su
  2     | godman(ssh key)                      | godman
  3     | wangheng(ssh key)                    | wangheng
提示：输入资产[hw-bj-yw-work-03(10.211.4.113)]的账号ID
返回：B/b
"""


class JumpServerAccountSelectionTest(unittest.TestCase):
    def test_parse_account_options_from_jumpserver_table(self):
        accounts = _parse_account_options(ACCOUNT_TABLE)

        self.assertEqual(
            accounts,
            [
                {"id": "1", "name": "__su(ssh key)", "username": "__su"},
                {"id": "2", "name": "godman(ssh key)", "username": "godman"},
                {"id": "3", "name": "wangheng(ssh key)", "username": "wangheng"},
            ],
        )

    def test_selects_preferred_account_by_username_or_base_name(self):
        config = GatewayConfig(
            name="ttyuyin-prod",
            type="interactive_expect",
            command="ssh jump",
            target_prompt_patterns=[],
            shell_prompt_patterns=[],
            account_prompt_patterns=[r"ID>\s*"],
            preferred_account="__su",
        )

        self.assertEqual(_select_account_id(config, "10.211.4.113", ACCOUNT_TABLE), "1")

    def test_host_override_wins_for_multi_jumpserver_assets(self):
        config = GatewayConfig(
            name="ttyuyin-test",
            type="interactive_expect",
            command="ssh jump",
            target_prompt_patterns=[],
            shell_prompt_patterns=[],
            account_prompt_patterns=[r"ID>\s*"],
            preferred_account="godman",
            account_id_by_host={"10.198.1.213": "2"},
        )

        self.assertEqual(_select_account_id(config, "10.198.1.213", ACCOUNT_TABLE), "2")

    def test_missing_preferred_account_reports_available_accounts(self):
        config = GatewayConfig(
            name="ttyuyin-prod",
            type="interactive_expect",
            command="ssh jump",
            target_prompt_patterns=[],
            shell_prompt_patterns=[],
            account_prompt_patterns=[r"ID>\s*"],
            preferred_account="missing-user",
        )

        with self.assertRaises(ToolExecutionError) as ctx:
            _select_account_id(config, "10.211.4.113", ACCOUNT_TABLE)

        message = str(ctx.exception)
        self.assertIn("missing-user", message)
        self.assertIn("__su", message)
        self.assertIn("godman", message)

    def test_account_prompt_wins_over_broad_shell_prompt(self):
        config = GatewayConfig(
            name="ttyuyin-prod",
            type="interactive_expect",
            command="ssh jump",
            target_prompt_patterns=[],
            shell_prompt_patterns=[r"[$#>] "],
            account_prompt_patterns=[r"ID>\s*"],
            preferred_account="__su",
        )
        child = FakeChild(
            matches=[0, 1],
            befores=[ACCOUNT_TABLE, "connected\n"],
        )

        from ssh_assist_mcp.gateway import GatewaySSHRunner

        GatewaySSHRunner(config)._expect_shell_or_select_account(child, "10.211.4.113")

        self.assertEqual(child.patterns_seen[0], [r"ID>\s*", r"[$#>] "])
        self.assertEqual(child.sent, ["1\r"])

    def test_split_account_prompt_is_not_mistaken_for_shell(self):
        config = GatewayConfig(
            name="ttyuyin-prod",
            type="interactive_expect",
            command="ssh jump",
            target_prompt_patterns=[],
            shell_prompt_patterns=[r"[$#>] "],
            account_prompt_patterns=[r"ID>\s*"],
            preferred_account="__su",
        )
        child = FakeChild(
            matches=[1, 1],
            befores=[ACCOUNT_TABLE + "ID", "connected\n"],
            afters=["> ", "# "],
        )

        from ssh_assist_mcp.gateway import GatewaySSHRunner

        GatewaySSHRunner(config)._expect_shell_or_select_account(child, "10.211.4.113")

        self.assertEqual(child.sent, ["1\r"])

    def test_matcher_driven_login_sends_host_selects_account_and_stops_at_shell(self):
        config = GatewayConfig(
            name="ttyuyin-prod",
            type="interactive_expect",
            command="ssh jump",
            target_prompt_patterns=[r"legacy-target"],
            shell_prompt_patterns=[r"legacy-shell"],
            account_prompt_patterns=[r"legacy-account"],
            preferred_account="__su",
        )
        child = FakeChild(
            matches=[0, 0, 0, 0],
            befores=["", ACCOUNT_TABLE, "ID", "connected\n"],
            afters=["请输入资产 IP:", "提示：输入资产账号ID", "> ", "[root@app ~]# "],
        )

        from ssh_assist_mcp.gateway import GatewaySSHRunner

        GatewaySSHRunner(config, matcher_registry=MatcherRegistry())._drive_matcher_login(child, "10.211.4.113")

        self.assertEqual(child.sent, ["10.211.4.113\r", "1\r"])
        self.assertNotIn([r"legacy-target"], child.patterns_seen)

    def test_matcher_driven_login_uses_accumulated_transcript_for_split_account_prompt(self):
        config = GatewayConfig(
            name="ttyuyin-prod",
            type="interactive_expect",
            command="ssh jump",
            target_prompt_patterns=[],
            shell_prompt_patterns=[],
            account_prompt_patterns=[],
            preferred_account="__su",
        )
        child = FakeChild(
            matches=[0, 0, 0],
            befores=["", ACCOUNT_TABLE + "\nID", "connected\n"],
            afters=["Opt> ", "> ", "[root@app ~]# "],
        )

        from ssh_assist_mcp.gateway import GatewaySSHRunner

        GatewaySSHRunner(config, matcher_registry=MatcherRegistry())._drive_matcher_login(child, "10.211.4.113")

        self.assertEqual(child.sent, ["10.211.4.113\r", "1\r"])

    def test_matcher_driven_login_can_return_probe_steps_without_remote_command(self):
        config = GatewayConfig(
            name="ttyuyin-prod",
            type="interactive_expect",
            command="ssh jump",
            target_prompt_patterns=[],
            shell_prompt_patterns=[],
            account_prompt_patterns=[],
            preferred_account="__su",
        )
        child = FakeChild(
            matches=[0, 0, 0],
            befores=["", ACCOUNT_TABLE + "\nID", "connected\n"],
            afters=["Opt> ", "> ", "[root@app ~]# "],
        )

        from ssh_assist_mcp.gateway import GatewaySSHRunner

        steps = GatewaySSHRunner(config, matcher_registry=MatcherRegistry())._drive_matcher_login(
            child, "10.211.4.113", collect_trace=True
        )

        self.assertEqual([step["action"]["type"] for step in steps], ["send_text", "send_text", "shell_reached"])
        self.assertEqual(steps[-1]["last_state"], "shell")
        self.assertEqual(child.sent, ["10.211.4.113\r", "1\r"])

    def test_clean_gateway_output_filters_standalone_quote_echo(self):
        output = """
'
__SSH_ASSIST_DONE_demo__:BEGIN
'
== downloads dir ==
total 2.4G
__SSH_ASSIST_DONE_demo__:END:0
"""

        cleaned = _clean_gateway_output(output, "ls -lah /data/downloads", "__SSH_ASSIST_DONE_demo__")

        self.assertEqual(cleaned, "== downloads dir ==\ntotal 2.4G\n")

    def test_clean_gateway_output_filters_escaped_newline_quote_echo(self):
        output = """
__SSH_ASSIST_DONE_demo__:BEGIN
\\n'
ok
Wed Jun 24 08:58:40 PM CST 2026
__SSH_ASSIST_DONE_demo__:END:0
"""

        cleaned = _clean_gateway_output(output, "echo ok; date", "__SSH_ASSIST_DONE_demo__")

        self.assertEqual(cleaned, "ok\nWed Jun 24 08:58:40 PM CST 2026\n")


class FakeChild:
    def __init__(self, matches, befores, afters=None):
        self.matches = list(matches)
        self.befores = list(befores)
        self.afters = list(afters or ["" for _ in matches])
        self.patterns_seen = []
        self.sent = []
        self.before = ""
        self.after = ""

    def expect(self, patterns, timeout):
        self.patterns_seen.append(patterns)
        self.before = self.befores.pop(0)
        self.after = self.afters.pop(0)
        return self.matches.pop(0)

    def send(self, value):
        self.sent.append(value)


if __name__ == "__main__":
    unittest.main()

# Codex 安装配置

通用安装流程先看：[任意 Agent 安装 MCP](agent.md)。

在 Codex 的 MCP 配置中加入本项目 server。

把下面的 `/path/to/jumpserver_ssh_mcp` 替换为本项目绝对路径。

示例：

```toml
[mcp_servers.jumpserver-ssh-mcp]
command = "/path/to/jumpserver_ssh_mcp/.venv/bin/jumpserver-ssh-mcp"

[mcp_servers.jumpserver-ssh-mcp.env]
SSH_ASSIST_PROFILE = "/Users/you/jumpserver-ssh-mcp/config/local.yaml"
SSH_ASSIST_AUDIT_LOG = "/Users/you/jumpserver-ssh-mcp/logs/jumpserver-ssh-mcp-audit.jsonl"
```

配置后重启或 reload Codex。

验证：

- 能看到 `ssh.run_command` 等 SSH tools。
- 能看到 `ssh.matcher_list`、`ssh.matcher_validate`、`ssh.matcher_test_transcript`。
- 能读取 `jumpserver-ssh-mcp://docs/matchers/guide`。

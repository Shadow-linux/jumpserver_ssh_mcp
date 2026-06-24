# opencode 安装配置

通用安装流程先看：[任意 Agent 安装 MCP](agent.md)。

在 opencode 的 MCP 配置中加入本项目 server。

把下面的 `/path/to/jumpserver_ssh_mcp` 替换为本项目绝对路径。

示例：

```json
{
  "mcp": {
    "jumpserver-ssh-mcp": {
      "command": "/path/to/jumpserver_ssh_mcp/.venv/bin/jumpserver-ssh-mcp",
      "env": {
        "SSH_ASSIST_PROFILE": "/Users/you/jumpserver-ssh-mcp/config/local.yaml",
        "SSH_ASSIST_AUDIT_LOG": "/Users/you/jumpserver-ssh-mcp/logs/jumpserver-ssh-mcp-audit.jsonl"
      }
    }
  }
}
```

配置后重启或 reload opencode。

验证：

- `ssh.run_command` 可见。
- `ssh.matcher_list` 可见。
- `jumpserver-ssh-mcp://docs/matchers/guide` 可读。

# Kimi CLI 安装配置

通用安装流程先看：[任意 Agent 安装 MCP](agent.md)。

在 Kimi CLI 的 MCP server 配置中加入本项目 server。

把下面的 `/path/to/jumpserver_ssh_mcp` 替换为本项目绝对路径。

示例：

```json
{
  "mcpServers": {
    "jumpserver-ssh-mcp": {
      "command": "/path/to/jumpserver_ssh_mcp/.venv/bin/jumpserver-ssh-mcp",
      "env": {
        "SSH_ASSIST_PROFILE": "/path/to/jumpserver_ssh_mcp/config/local.yaml",
        "SSH_ASSIST_AUDIT_LOG": "/path/to/jumpserver_ssh_mcp/logs/jumpserver-ssh-mcp-audit.jsonl"
      }
    }
  }
}
```

配置后重启或 reload Kimi CLI。

验证：

- tools 中能看到 SSH tools 和 matcher tools。
- resources 中能看到 matcher guide、example、schema、troubleshooting。

# 任意 Agent 安装 jumpserver-ssh-mcp

这份文档解决一件事：让任意支持 MCP 的 Agent 客户端安装并启动 `jumpserver-ssh-mcp`。

配套的 `jumpserver-agent-skill` 负责指导 Agent 怎么配置 gateway、probe、smoke test、修 matcher；但安装 MCP 本体只需要下面这些步骤。

## 1. 准备项目目录

从源码安装时，先把项目放到一个稳定路径，例如：

```bash
git clone <repo-url> jumpserver_ssh_mcp
cd jumpserver_ssh_mcp
```

安装依赖和 MCP server：

```bash
uv venv
uv pip install -e '.[mcp]'
```

安装后应该能看到启动命令：

```bash
.venv/bin/jumpserver-ssh-mcp
```

## 2. 准备 profile

profile 是 MCP 启动时读取的 JumpServer 配置。

发布样例：

```text
config/example.yaml
```

完整参考：

```text
config/full-example.yaml
```

本机真实配置建议放：

```text
config/local.yaml
```

最小格式：

```yaml
gateways:
  pro-jumpserver:
    command: ssh -i ~/.ssh/pro.pem ops@jump.example.com -p2222
    matcher: builtin-generic
```

如果有多个资产账号，可以加：

```yaml
preferred_account: __su
```

## 3. MCP 客户端配置模型

所有 Agent 客户端最终都要表达同一组信息：

```text
server name: jumpserver-ssh-mcp
command: /path/to/jumpserver_ssh_mcp/.venv/bin/jumpserver-ssh-mcp
env.SSH_ASSIST_PROFILE: /path/to/jumpserver_ssh_mcp/config/local.yaml
env.SSH_ASSIST_AUDIT_LOG: /path/to/jumpserver_ssh_mcp/logs/jumpserver-ssh-mcp-audit.jsonl
```

`SSH_ASSIST_AUDIT_LOG` 是审计日志基础路径；运行时会按 UTC 日期写入 `jumpserver-ssh-mcp-audit-YYYY-MM-DD.jsonl`。

不同客户端只是配置文件格式不同。

## 4. Codex 示例

写入 `~/.codex/config.toml`：

```toml
[mcp_servers.jumpserver-ssh-mcp]
command = "/path/to/jumpserver_ssh_mcp/.venv/bin/jumpserver-ssh-mcp"

[mcp_servers.jumpserver-ssh-mcp.env]
SSH_ASSIST_PROFILE = "/path/to/jumpserver_ssh_mcp/config/local.yaml"
SSH_ASSIST_AUDIT_LOG = "/path/to/jumpserver_ssh_mcp/logs/jumpserver-ssh-mcp-audit.jsonl"
```

改完后重启 Codex 或新开线程。

## 5. JSON 客户端示例

很多 Agent 客户端使用 JSON 风格 MCP 配置。

常见 `mcpServers` 格式：

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

常见 `mcp` 格式：

```json
{
  "mcp": {
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

## 6. 安装后验证

先用同样的环境变量直接启动 server，确认不会立刻报错：

```bash
SSH_ASSIST_PROFILE=/path/to/jumpserver_ssh_mcp/config/local.yaml \
SSH_ASSIST_AUDIT_LOG=/path/to/jumpserver_ssh_mcp/logs/jumpserver-ssh-mcp-audit.jsonl \
/path/to/jumpserver_ssh_mcp/.venv/bin/jumpserver-ssh-mcp
```

然后在 Agent 客户端里确认能看到工具：

```text
ssh.matcher_list
ssh.matcher_validate
ssh.matcher_probe
ssh.matcher_test_transcript
ssh.run_command
ssh.run_script
```

确认能读取资源：

```text
jumpserver-ssh-mcp://docs/matchers/guide
jumpserver-ssh-mcp://docs/matchers/schema
```

最后调用：

```text
ssh.matcher_list
```

如果能看到配置里的 gateway，MCP 安装就完成了。

## 7. 下一步交给 skill

MCP 装好后，让 Agent 读取或安装：

```text
skills/jumpserver-agent-skill
```

它会继续指导 Agent：

- 新增 gateway
- probe JumpServer
- smoke test
- matcher 失败时编写自定义 matcher

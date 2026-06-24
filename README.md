# jumpserver-ssh-mcp

`jumpserver-ssh-mcp` 是一个 MCP Server，用来让 Agent 通过直连 SSH 或 JumpServer 入口安全地执行远程命令。

产品方向是 **MCP only**：

- `gateway` 表示一个 JumpServer / 环境入口。
- 入口匹配插件负责适配不同 JumpServer 交互界面。
- 到达目标机器 shell 后，继续复用现有 SSH 执行、安全检查、审计和输出收集机制。
- 不新增 CLI 产品工作流；仓库里保留的 CLI 只用于兼容和本地 smoke check。

## 当前状态

这个项目原来是 `ssh-assist-mcp` 原型，已经具备：

- `ssh.run_command`
- `ssh.run_script`
- `ssh.rsync_upload`
- `ssh.rsync_download`
- 基础安全策略和审计日志
- 基础 JumpServer 交互式 gateway 执行

现在要产品化的是 JumpServer 入口层：

- matcher plugin 契约和 registry
- 内置通用 JumpServer matcher
- 用户自写声明式 matcher
- 多 JumpServer / 多环境 gateway 自由切换
- MCP resources 暴露 matcher 编写文档、示例、schema、排障说明
- README 和 `docs/install/*` 提供 Codex、Kimi CLI、opencode 安装入口

## 安装入口

安装文档是普通仓库文件，所以 **MCP 还没装好之前也能看**：

- [任意 Agent 安装 MCP](docs/install/agent.md)
- [Codex 安装配置](docs/install/codex.md)
- [Kimi CLI 安装配置](docs/install/kimi-cli.md)
- [opencode 安装配置](docs/install/opencode.md)

推荐顺序：

1. 先按 [任意 Agent 安装 MCP](docs/install/agent.md) 把 `jumpserver-ssh-mcp` 接入 Agent 客户端。
2. 再让 Agent 安装或读取 `skills/jumpserver-agent-skill`。
3. Agent 按 skill 创建 profile、配置 gateway、probe、smoke test，必要时编写 matcher。

MCP 安装完成后，Agent 可以再通过 MCP resources 读取运行时文档，例如 matcher 编写指南、示例、schema 和 troubleshooting。

## 快速初始化

从源码安装时，先把项目拉到一个稳定目录：

```bash
git clone <repo-url> jumpserver_ssh_mcp
cd jumpserver_ssh_mcp
```

创建虚拟环境并安装 MCP server：

```bash
uv venv
uv pip install -e '.[mcp]'
```

确认启动命令存在：

```bash
.venv/bin/jumpserver-ssh-mcp
```

准备本机 profile。运行期文件统一放在用户目录，避免更新源码仓库时覆盖本机配置：

```bash
mkdir -p ~/jumpserver-ssh-mcp/{config,logs,matchers}
cp config/example.yaml ~/jumpserver-ssh-mcp/config/local.yaml
```

配置文件说明：

- `config/example.yaml`：推荐起步样例，只包含人类需要维护的最小字段。
- `config/full-example.yaml`：完整参考样例，给 Agent 或高级用户查看所有可选字段。
- `~/jumpserver-ssh-mcp/config/local.yaml`：本机真实配置，不放在源码仓库里。

然后把 `~/jumpserver-ssh-mcp/config/local.yaml` 改成真实 JumpServer：

```yaml
gateways:
  pro-jumpserver:
    command: ssh -i ~/.ssh/pro.pem ops@jump.example.com -p2222
    matcher: builtin-generic
```

在任意支持 MCP 的 Agent 客户端里配置：

```text
server name: jumpserver-ssh-mcp
command: /path/to/jumpserver_ssh_mcp/.venv/bin/jumpserver-ssh-mcp
env.SSH_ASSIST_PROFILE: /Users/you/jumpserver-ssh-mcp/config/local.yaml
env.SSH_ASSIST_AUDIT_LOG: /Users/you/jumpserver-ssh-mcp/logs/jumpserver-ssh-mcp-audit.jsonl
```

配置后重启或 reload Agent 客户端，然后验证：

```text
ssh.matcher_list
```

能看到 profile 里的 gateway，就说明 MCP 初始化完成。

## 从 v0.1.0 升级

`0.2.1` 起推荐把运行期文件放到 `~/jumpserver-ssh-mcp/`。如果旧版本已经在 MCP 客户端里显式配置了 `SSH_ASSIST_PROFILE`，升级后会继续优先使用这个路径。

如果旧配置还在源码仓库里，可以迁移一份：

```bash
mkdir -p ~/jumpserver-ssh-mcp/{config,logs,matchers}
cp config/local.yaml ~/jumpserver-ssh-mcp/config/local.yaml
```

为了兼容旧安装，无显式 `SSH_ASSIST_PROFILE` 时会按顺序查找：

1. `~/jumpserver-ssh-mcp/config/local.yaml`
2. `config/local.yaml`
3. `config/example.yaml`

## Gateway 是环境入口

调用 MCP 工具时用 `gateway` 选择要进入哪个 JumpServer / 环境：

```text
gateway=prod-jumpserver  -> 生产 JumpServer / 环境
gateway=test-jumpserver  -> 测试 JumpServer / 环境
gateway=ops-jumpserver   -> 运维 JumpServer / 环境
```

建议运维类调用都显式传 `gateway`，这样审计日志能清楚记录 Agent 进入了哪个环境入口。

## Matcher 插件放在哪里

内置通用 matcher 和 reference matcher 会随 Python 包一起分发，安装后默认可用：

- `builtin-generic`
- `ttyuyin-opt-account`
- `qmzy-asset-list-id`

用户自写 matcher 推荐放在用户运行目录：

- 用户运行目录：`~/jumpserver-ssh-mcp/matchers/`

然后在 profile 中配置：

```yaml
matchers:
  custom_dirs:
    - ~/jumpserver-ssh-mcp/matchers
```

每个 gateway 可以绑定自己的 matcher：

```yaml
default_gateway: jumpserver-test

gateways:
  jumpserver-test:
    command: ssh -i ~/.ssh/jumpserver-test.pem ops@jump-test.example.com -p2222
    matcher: builtin-generic
```

## Matcher 能做什么

Matcher 只负责 JumpServer 登录入口匹配，不能执行目标机器命令。

它可以返回这些动作：

- 发送目标 host/IP
- 从主机候选列表中选择目标
- 从账号表中选择账号
- 报告已经到达 shell
- 报告未匹配，并返回脱敏 transcript 片段给 Agent 修插件

远程命令仍由 `ssh.run_command` / `ssh.run_script` 统一执行。

## MCP Tools

已有 SSH tools：

- `ssh.run_command`
- `ssh.run_script`
- `ssh.rsync_upload`
- `ssh.rsync_download`

Matcher tools：

- `ssh.matcher_list`
- `ssh.matcher_validate`
- `ssh.matcher_probe`
- `ssh.matcher_test_transcript`

`ssh.matcher_probe` 只验证 matcher 能否通过 JumpServer 到达目标 shell，不执行目标机器命令。

## 安全与审计

远程命令会经过 `SafetyPolicy` 评估。

高风险操作必须显式确认。审计日志基础路径默认是 `~/jumpserver-ssh-mcp/logs/jumpserver-ssh-mcp-audit.jsonl`，也可以通过 `SSH_ASSIST_AUDIT_LOG` 指定；实际写入时会按 UTC 日期滚动为 `~/jumpserver-ssh-mcp/logs/jumpserver-ssh-mcp-audit-YYYY-MM-DD.jsonl`。

不要把私钥内容、明文密码、token 写进 profile、matcher、文档或审计日志。

## 开发验证

运行单元测试：

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

运行 MCP server：

```bash
SSH_ASSIST_PROFILE=config/example.yaml .venv/bin/jumpserver-ssh-mcp
```

旧原型入口 `ssh-assist-mcp` 暂时保留为兼容别名。

构建 wheel：

```bash
uv build --wheel
```

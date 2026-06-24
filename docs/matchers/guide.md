# Matcher 插件编写指南

Matcher 插件用于适配 JumpServer 入口界面。它只处理登录交互，不执行目标机器命令。

## Agent 职责边界

人类只需要提供 JumpServer SSH 登录方式、gateway 名称和一个目标 host/IP 或资产标识。Agent 应自行完成 profile 配置、matcher 选择、probe 验证和 smoke test。

如果内置 matcher 不能匹配当前 JumpServer 返回的界面，Agent 应自行编写自定义 matcher，而不是要求人类填写正则、prompt 或交互细节。

内置 matcher 随 MCP 包分发，安装后默认可用。自定义 matcher 应写入 profile 中配置的 `matchers.custom_dirs` 目录，例如：

```yaml
matchers:
  custom_dirs:
    - ~/jumpserver-ssh-mcp/matchers
```

不要修改 MCP 包内置的 reference matcher 文件。

## 基本流程

1. Agent 连接 JumpServer 后读取当前 screen。
2. Matcher 根据 screen 判断状态。
3. Matcher 返回一个交互动作。
4. Gateway runner 发送动作。
5. 到达目标 shell 后，交给 `ssh.run_command` / `ssh.run_script` 执行命令。

## 状态

- `target_prompt`：JumpServer 正在要求输入 host/IP。
- `host_candidates`：JumpServer 返回多个主机候选，需要选择目标。
- `account_prompt`：JumpServer 要求选择账号。
- `shell`：已经到达目标机器 shell。
- `unknown`：当前 screen 未匹配。

## 动作

- `send_text`：发送文本并回车，例如 host/IP 或账号 ID。
- `wait`：当前 screen 已识别，但输入点还没出现，继续读取下一屏。
- `shell_reached`：报告已经到达 shell。

Matcher 不能返回“执行远程命令”动作。

## 声明式 matcher

最小 JSON：

```json
{
  "name": "my-jumpserver",
  "target_prompt_patterns": ["请输入.*(主机|资产|IP)", "(?i)input.*(host|ip)"],
  "account_prompt_patterns": ["账号.*ID", "(?i)account.*id"],
  "shell_prompt_patterns": ["[$#>]\\\\s*$"]
}
```

如果 JumpServer 需要先从菜单进入资产列表，例如先在 `Opt>` 输入 `p`，再在 `[Host]>` 输入资产 ID，可以这样写：

```json
{
  "name": "qmzy-asset-list-id",
  "menu_prompt_patterns": ["Opt>\\\\s*$"],
  "menu_action_value": "p",
  "target_prompt_patterns": ["\\\\[Host\\\\]>\\\\s*$"],
  "shell_prompt_patterns": ["[$#>]\\\\s*$"]
}
```

把文件放到 `~/jumpserver-ssh-mcp/matchers/`，并在 profile 中配置：

```yaml
matchers:
  custom_dirs:
    - ~/jumpserver-ssh-mcp/matchers
```

## 验证流程

1. 用 `ssh.matcher_validate` 校验 matcher 文件。
2. 用 `ssh.matcher_test_transcript` 对真实或脱敏 transcript 做 replay。
3. 用 `ssh.matcher_probe` 做 live 登录验证，只确认能到达 shell，不执行目标机器命令。
4. matcher 能走到 `shell_reached` 后，再用 gateway 执行只读 smoke command。

## 安全规则

- 不写入明文密码。
- 不写入私钥内容。
- 不在 matcher 里执行目标机器命令。
- 失败 transcript 返回前必须脱敏。

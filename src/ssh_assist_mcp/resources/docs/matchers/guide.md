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

常用验证流程：

1. 用 `ssh.matcher_validate` 校验 matcher 文件。
2. 用 `ssh.matcher_test_transcript` 对真实或脱敏 transcript 做 replay。
3. 用 `ssh.matcher_probe` 做 live 登录验证，只确认能到达 shell，不执行目标机器命令。
4. 到达 `shell_reached` 后，再用 gateway 执行只读 smoke command。

支持动作：

- `send_text`：发送文本并回车。
- `wait`：当前 screen 已识别，但输入点还没出现，继续读取下一屏。
- `shell_reached`：报告已经到达目标 shell。

安全规则：

- 不写入明文密码。
- 不写入私钥内容。
- 不在 matcher 里执行目标机器命令。

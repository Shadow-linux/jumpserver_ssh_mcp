# Matcher 排障

## host/IP 没有发送

检查 `target_prompt_patterns` 是否能匹配 JumpServer 当前 screen。中英文界面建议都写。

## 账号没有选中

检查账号表是否是 `ID | 名称 | 用户名` 结构。优先使用 profile 里的 `preferred_account` 或 `account_id_by_host`。

## shell 被误判

收窄 `shell_prompt_patterns`，避免把 JumpServer 菜单提示符误判成目标机器 shell。

## 自定义 matcher 没加载

检查：

- 文件是否是 `.json`。
- `matchers.custom_dirs` 是否包含该目录。
- `name` 是否和内置 matcher 或其他自定义 matcher 重名。

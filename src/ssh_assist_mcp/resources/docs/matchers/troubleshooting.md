# Matcher 排障

## 没有发送 host/IP

检查 `target_prompt_patterns` 是否能匹配 JumpServer 当前 screen。菜单说明文字不要写成过宽规则。

## 账号没有选中

检查账号表是否包含 `ID | 名称 | 用户名`。如果账号表和 `ID>` 分屏出现，matcher 应先返回 `wait`。

## shell 被误判

收窄 `shell_prompt_patterns`，避免把 JumpServer 菜单提示符误判成目标机器 shell。

## 自定义 matcher 没加载

检查文件是否是 `.json`，以及 `matchers.custom_dirs` 是否包含该目录。

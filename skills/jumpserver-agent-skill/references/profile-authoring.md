# Profile Authoring

Use this when creating or updating the file referenced by `SSH_ASSIST_PROFILE`.

Start from `config/example.yaml` for normal onboarding. Use `config/full-example.yaml` only when the Agent needs to inspect all supported fields or maintain legacy compatibility options.

For v0.1.0 upgrades, check whether the human already has a repo-local `config/local.yaml` or an existing `SSH_ASSIST_PROFILE`. Preserve that working profile first, then migrate a copy to `/Users/you/jumpserver-ssh-mcp/config/local.yaml` when the human wants the new runtime layout.

## Product-Facing Shape

Keep human-maintained profiles small:

```yaml
gateways:
  pro-jumpserver:
    command: ssh -i ~/.ssh/pro.pem ops@jump.example.com -p2222
    matcher: builtin-generic
    preferred_account: __su
    command_timeout: 1800

matchers:
  custom_dirs:
    - ~/jumpserver-ssh-mcp/matchers
```

Required per gateway:

- `command`

Optional per gateway:

- `matcher`; defaults to `builtin-generic`
- `preferred_account`; useful when JumpServer shows multiple asset accounts
- `command_timeout`; defaults to `1800` seconds for command execution

Optional top-level:

- `default_gateway`; omit it when explicit gateway selection is safer
- `matchers.custom_dirs`; directories where Agent-authored matcher JSON files are stored

## Matcher File Ownership

Do not create or edit packaged reference matcher files. Those are owned by `jumpserver-ssh-mcp` and are loaded automatically after installation.

When the Agent needs to author a new matcher, write it to one configured custom directory:

- user runtime directory: `~/jumpserver-ssh-mcp/matchers/`

If the profile does not already include a custom matcher directory, add:

```yaml
matchers:
  custom_dirs:
    - ~/jumpserver-ssh-mcp/matchers
```

## What Not To Ask Humans To Fill

Do not ask humans to write these unless maintaining legacy config:

- `type`
- `login_prompt_patterns`
- `target_prompt_patterns`
- `shell_prompt_patterns`
- `account_prompt_patterns`
- `connect_timeout`
- `max_attempts`
- `retry_delay_seconds`
- `privilege_escalation`

The MCP has defaults and matcher plugins for these concerns.

## Matcher Choice

Start with:

```yaml
matcher: builtin-generic
```

Use known reference matchers when the gateway matches a proven flow:

```yaml
matcher: ttyuyin-opt-account
matcher: qmzy-asset-list-id
```

Create a custom matcher only after `ssh.matcher_probe` fails with an unmatched JumpServer screen.

## Editing Rules

- Preserve existing gateways unless the human asks to remove them.
- Do not store passwords, private key contents, tokens, or secrets.
- Prefer `~/.ssh/key-name.pem` paths in commands.
- For production gateways, keep command execution explicitly gated by the human.

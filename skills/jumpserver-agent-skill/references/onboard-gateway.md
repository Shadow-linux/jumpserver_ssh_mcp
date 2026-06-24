# Gateway Onboarding Playbook

## Simple Profile Shape

Prefer this product-facing format:

```yaml
default_gateway: pro-jumpserver

gateways:
  pro-jumpserver:
    command: ssh -i ~/.ssh/pro.pem ops@jump.example.com -p2222
    matcher: builtin-generic
    preferred_account: __su

matchers:
  custom_dirs:
    - ~/jumpserver-ssh-mcp/matchers
```

## Onboarding Sequence

1. Create or update a profile file. Prefer a local file outside published examples when it contains real hostnames or user names.
2. Set `SSH_ASSIST_PROFILE` in the MCP client configuration to that profile path.
3. Use `ssh.matcher_list` and confirm the gateway appears.
4. Use `ssh.matcher_probe` with the provided target host.
5. On success, use `ssh.run_command` with `connection_mode: gateway`, explicit `gateway`, and a read-only command.
6. On failure, inspect the returned state, reason, and transcript excerpt.

## Matcher Repair Sequence

1. Read `jumpserver-ssh-mcp://docs/matchers/guide`.
2. Read `jumpserver-ssh-mcp://docs/matchers/schema`.
3. Create a JSON matcher under one configured custom matcher directory, not under the packaged reference matcher directory.
4. Validate it with `ssh.matcher_validate`.
5. Replay the failed screen with `ssh.matcher_test_transcript`.
6. Bind the matcher name to the gateway.
7. Rerun `ssh.matcher_probe`.

## Success Evidence

Record:

- gateway name
- JumpServer command shape, with secrets omitted
- matcher name
- target host used for probe
- probe result
- smoke command and summarized output

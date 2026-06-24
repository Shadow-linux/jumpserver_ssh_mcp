---
name: jumpserver-agent-skill
description: Use when an Agent needs to configure, validate, or repair jumpserver-ssh-mcp access for a JumpServer gateway, especially when the human provides a gateway name, SSH login command, target host, or a failed JumpServer login transcript.
---

# JumpServer Agent Skill

## Overview

Use `jumpserver-ssh-mcp` as the capability layer and this skill as the operating playbook. The human should only need to provide a gateway name, a JumpServer SSH login command, and a target host; the Agent owns configuration, probe, smoke test, and matcher repair.

## Agent Responsibility

The Agent must perform the operational setup work itself. Do not ask the human to hand-write profile internals or matcher JSON unless they explicitly want to.

Human-provided inputs should stay small:

- gateway name
- JumpServer SSH login command
- target host/IP or asset identifier for validation
- optional preferred asset account

Agent-owned outputs:

- MCP client configuration
- `SSH_ASSIST_PROFILE` profile file
- gateway entry
- matcher selection
- custom matcher JSON when built-in matchers fail
- probe and smoke-test evidence

Built-in matchers are packaged inside `jumpserver-ssh-mcp` and are available after installation. Agent-authored matchers should be written only to configured custom matcher directories, usually `matchers/custom/` for a project or `~/.config/jumpserver-ssh-mcp/matchers/` for a user.

## Required Inputs

Ask for only missing essentials:

- `gateway_name`, such as `pro-jumpserver` or `test-jumpserver`
- JumpServer SSH login command, such as `ssh -i ~/.ssh/pro.pem ops@jump.example.com -p2222`
- one target host or asset identifier for validation

Optional:

- preferred asset account, such as `root`, `__su`, or `deploy`
- environment label, such as `prod` or `test`

## Workflow

1. If the MCP server is not installed in the current Agent client, read `references/mcp-client-config.md` and configure it.
2. Read `references/profile-authoring.md` before creating or changing a profile file.
3. Read `references/onboard-gateway.md` before probing a gateway.
4. Create or update the profile using the simple gateway shape; do not expose internal fields like `type: interactive_expect` unless maintaining legacy config.
5. Start with `matcher: builtin-generic` unless a known reference matcher fits better.
6. Call `ssh.matcher_list` to verify available matchers and configured gateways.
7. Call `ssh.matcher_probe` with the target host and gateway. This must not execute a remote command.
8. If probe succeeds, run one non-destructive smoke command with `ssh.run_command`, such as `hostname; whoami; id`.
9. If probe fails because the JumpServer screen is not matched, read the MCP matcher docs and write a custom declarative matcher.
10. Validate custom matcher with `ssh.matcher_validate`, replay transcript snippets with `ssh.matcher_test_transcript`, then rerun `ssh.matcher_probe`.
11. Record the final gateway name, profile path, matcher name, target used for validation, and smoke evidence.

## Safety Rules

- Never put private key contents, passwords, tokens, or secrets into profile files, matcher files, docs, or audit notes.
- Do not run destructive commands during onboarding. Use read-only smoke commands.
- Treat production gateways as explicit human-gated environments.
- If `ssh.run_command` reports a safety confirmation requirement, stop and ask the human before continuing.

## MCP Docs To Read When Needed

- `jumpserver-ssh-mcp://docs/matchers/guide`
- `jumpserver-ssh-mcp://docs/matchers/example`
- `jumpserver-ssh-mcp://docs/matchers/schema`
- `jumpserver-ssh-mcp://docs/matchers/troubleshooting`

## Common Failure Paths

- Gateway not visible: check the profile path used by `SSH_ASSIST_PROFILE`.
- MCP tools not visible: check the client config, restart/reload the client, then verify the server command starts.
- Built-in matcher fails: capture the unmatched transcript excerpt from `ssh.matcher_probe` and create a custom matcher.
- Multiple accounts appear: set `preferred_account` in the gateway profile or matcher context.
- Wrong environment: require explicit `gateway` in every command instead of relying on default gateway.

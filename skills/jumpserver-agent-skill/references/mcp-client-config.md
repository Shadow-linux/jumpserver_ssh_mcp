# MCP Client Configuration

Use this when `jumpserver-ssh-mcp` tools are not visible in the current Agent client.

## Inputs

- absolute project path
- profile path
- audit log path

If the human does not provide paths, infer:

```text
project path = current jumpserver_ssh_mcp repo
profile path = <project>/config/local.yaml for local real gateways
profile path = <project>/config/example.yaml for documentation-only smoke
audit log = <project>/logs/jumpserver-ssh-mcp-audit.jsonl
```

## Codex

Write or update `~/.codex/config.toml`:

```toml
[mcp_servers.jumpserver-ssh-mcp]
command = "/path/to/jumpserver_ssh_mcp/.venv/bin/jumpserver-ssh-mcp"

[mcp_servers.jumpserver-ssh-mcp.env]
SSH_ASSIST_PROFILE = "/path/to/jumpserver_ssh_mcp/config/local.yaml"
SSH_ASSIST_AUDIT_LOG = "/path/to/jumpserver_ssh_mcp/logs/jumpserver-ssh-mcp-audit.jsonl"
```

Back up the file before editing. Restart Codex or open a new Codex thread after changing MCP config.

## Kimi CLI

Add this server entry to the client MCP JSON:

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

## opencode

Add this server entry to the client MCP JSON:

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

## Verification

1. Parse the client config if it is TOML/JSON.
2. Start the MCP command with the same env and confirm it stays alive briefly.
3. Restart/reload the Agent client.
4. Confirm tools include `ssh.matcher_list` and `ssh.run_command`.
5. Call `ssh.matcher_list` and check the expected gateways.

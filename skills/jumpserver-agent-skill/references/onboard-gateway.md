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

## Owner Scoped Sessions

When the MCP tool accepts `owner_id`, pass a stable value for the current Agent/thread, such as `codex-thread-<thread-id>` or another human-readable unique id.

Rules:

- Use the same `owner_id` for retries from the same Agent/thread.
- Do not reuse another Agent's `owner_id`.
- The MCP records gateway SSH child processes under `~/jumpserver-ssh-mcp/run/sessions/<owner_id>/`.
- Before starting a new gateway SSH session, the MCP may clean child processes older than the 3-minute stale grace period recorded for the same `owner_id`.
- This same-owner cleanup is intended for interrupted Agent calls; it must not be used as a global SSH cleanup mechanism.
- If the human manually opened a JumpServer SSH terminal, do not claim or clean it unless the human explicitly asks.

## File Transfer

Use `ssh.file_push` and `ssh.file_pull` for single-file transfer through JumpServer gateways. They use base64 chunks and SHA256 verification, and do not require remote `rsync`.

Limits and routing:

- Use for files up to 50MB.
- Always pass explicit `connection_mode: gateway` and `gateway`.
- `ssh.file_push` writes to the remote filesystem and requires human confirmation.
- `ssh.file_pull` may copy sensitive remote data and requires human confirmation.
- Do not use `ssh.rsync_upload` or `ssh.rsync_download` with interactive JumpServer gateways; those tools are for direct SSH rsync only.

## Long Downloads And Builds

For package downloads, large file downloads, builds, and installs that may take minutes, prefer a background remote job plus short polling commands. Do not keep one foreground `ssh.run_command` call occupied when the task can safely continue on the remote host.

Recommended pattern:

1. Start the work with `nohup`, `systemd-run`, `tmux`, or another available background mechanism.
2. Redirect stdout/stderr to a known log file under `/tmp` or the task working directory.
3. Write a pid/status file when practical.
4. Poll with short read-only commands such as `ps`, `tail -n 80 <log>`, `stat`, `ls -lh`, checksum checks, or `systemctl status --no-pager`.
5. Stop polling when the expected file exists, the checksum matches, the process exits successfully, or the log reports completion.
6. If the background task is destructive, privileged, or production-impacting, ask the human before starting it.

Avoid re-running package installs or downloads blindly after a timeout. First check process state, lock files, logs, output files, and checksums.

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

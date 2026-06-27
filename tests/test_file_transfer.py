import base64
import hashlib
import re
import shlex
import tempfile
import unittest
from pathlib import Path

from ssh_assist_mcp.config import SSHConfig
from ssh_assist_mcp.errors import SafetyError, ToolExecutionError
from ssh_assist_mcp.result import CommandResult
from ssh_assist_mcp.ssh import SSHTool


class FakeRemoteSSHTool(SSHTool):
    def __init__(self, remote_root: Path):
        super().__init__(SSHConfig())
        self.remote_root = remote_root
        self.commands = []

    def _execute_remote_command(self, host, command, timeout, connection_mode, gateway):
        self.commands.append(command)
        if "wc -c <" in command:
            path = self._remote_path(command.split("<", 1)[1].strip())
            return CommandResult(["fake"], 0, f"{path.stat().st_size}\n", "")
        if command.startswith("sha256sum "):
            path = self._remote_path(command[len("sha256sum ") :].split("|", 1)[0].strip())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return CommandResult(["fake"], 0, f"{digest}  {path}\n", "")
        if command.startswith("base64 <"):
            path = self._remote_path(command[len("base64 <") :].strip())
            return CommandResult(["fake"], 0, base64.b64encode(path.read_bytes()).decode("ascii"), "")
        if "cat >>" in command:
            raw_path = re.search(r"cat >> ([^ ]+) <<", command).group(1)
            path = self._remote_path(raw_path)
            payload = command.split("\n", 1)[1].rsplit("\n__SSH_ASSIST_B64__", 1)[0]
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="ascii") as handle:
                handle.write(payload.strip() + "\n")
            return CommandResult(["fake"], 0, "", "")
        if "base64 -d" in command and "sha256sum" in command:
            b64_path = self._remote_path(re.search(r"base64 -d ([^ ]+)", command).group(1))
            final_path = self._remote_path(command.split(" > ", 1)[1].split(" && ", 1)[0])
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.write_bytes(base64.b64decode("".join(b64_path.read_text(encoding="ascii").split())))
            digest = hashlib.sha256(final_path.read_bytes()).hexdigest()
            b64_path.unlink(missing_ok=True)
            return CommandResult(["fake"], 0, f"{digest}  {final_path}\n", "")
        if command.startswith("mkdir -p ") and ": >" in command:
            quoted_dir = command.split("mkdir -p ", 1)[1].split(" && ", 1)[0]
            self._remote_path(quoted_dir).mkdir(parents=True, exist_ok=True)
            quoted_file = command.split(": >", 1)[1].strip()
            path = self._remote_path(quoted_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="ascii")
            return CommandResult(["fake"], 0, "", "")
        raise AssertionError(f"Unhandled remote command: {command}")

    def _remote_path(self, value: str) -> Path:
        unquoted = shlex.split(value)[0]
        return self.remote_root / unquoted.lstrip("/")


class FileTransferTest(unittest.TestCase):
    def test_file_push_transfers_file_and_returns_verified_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = root / "local.txt"
            local.write_text("hello jumpserver\n" * 3, encoding="utf-8")
            tool = FakeRemoteSSHTool(root / "remote")

            result = tool.file_push(
                "10.0.0.1",
                str(local),
                "/tmp/remote.txt",
                confirmed=True,
                connection_mode="gateway",
                gateway="demo",
                chunk_size=8,
            )

            remote = root / "remote" / "tmp" / "remote.txt"
            self.assertEqual(remote.read_bytes(), local.read_bytes())
            self.assertEqual(result["bytes"], local.stat().st_size)
            self.assertEqual(result["sha256"], hashlib.sha256(local.read_bytes()).hexdigest())
            self.assertTrue(result["verified"])
            self.assertEqual(result["direction"], "push")

    def test_file_pull_transfers_file_and_returns_verified_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = root / "remote" / "tmp" / "remote.txt"
            remote.parent.mkdir(parents=True)
            remote.write_bytes(b"remote-data\n" * 4)
            local = root / "downloaded.txt"
            tool = FakeRemoteSSHTool(root / "remote")

            result = tool.file_pull(
                "10.0.0.1",
                "/tmp/remote.txt",
                str(local),
                confirmed=True,
                connection_mode="gateway",
                gateway="demo",
            )

            self.assertEqual(local.read_bytes(), remote.read_bytes())
            self.assertEqual(result["bytes"], remote.stat().st_size)
            self.assertEqual(result["sha256"], hashlib.sha256(remote.read_bytes()).hexdigest())
            self.assertTrue(result["verified"])
            self.assertEqual(result["direction"], "pull")

    def test_file_push_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            local = Path(temp_dir) / "local.txt"
            local.write_text("secret", encoding="utf-8")
            tool = FakeRemoteSSHTool(Path(temp_dir) / "remote")

            with self.assertRaises(SafetyError):
                tool.file_push("10.0.0.1", str(local), "/tmp/remote.txt")

    def test_file_pull_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tool = FakeRemoteSSHTool(Path(temp_dir) / "remote")

            with self.assertRaises(SafetyError):
                tool.file_pull("10.0.0.1", "/tmp/remote.txt", str(Path(temp_dir) / "local.txt"))

    def test_file_push_rejects_files_over_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            local = Path(temp_dir) / "too-large.bin"
            local.write_bytes(b"x" * 11)
            tool = FakeRemoteSSHTool(Path(temp_dir) / "remote")

            with self.assertRaises(ToolExecutionError) as ctx:
                tool.file_push("10.0.0.1", str(local), "/tmp/remote.txt", confirmed=True, max_bytes=10)

            self.assertIn("exceeds max_bytes", str(ctx.exception))

    def test_file_pull_rejects_files_over_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            remote = root / "remote" / "tmp" / "too-large.bin"
            remote.parent.mkdir(parents=True)
            remote.write_bytes(b"x" * 11)
            tool = FakeRemoteSSHTool(root / "remote")

            with self.assertRaises(ToolExecutionError) as ctx:
                tool.file_pull("10.0.0.1", "/tmp/too-large.bin", str(root / "local.bin"), confirmed=True, max_bytes=10)

            self.assertIn("exceeds max_bytes", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

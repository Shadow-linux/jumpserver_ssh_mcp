import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ssh_assist_mcp.audit import AuditLogger


class AuditLoggerTest(unittest.TestCase):
    def test_record_writes_to_daily_log_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "jumpserver-ssh-mcp-audit.jsonl"
            logger = AuditLogger(str(base_path))

            with patch(
                "ssh_assist_mcp.audit.time.gmtime",
                return_value=time.strptime("2026-06-24T10:11:12Z", "%Y-%m-%dT%H:%M:%SZ"),
            ):
                logger.record(
                    "ssh.run_command",
                    "10.0.0.10",
                    "low",
                    {"command": "hostname", "token": "secret-value"},
                    "success",
                )

            daily_path = Path(temp_dir) / "jumpserver-ssh-mcp-audit-2026-06-24.jsonl"
            self.assertTrue(daily_path.exists())
            self.assertFalse(base_path.exists())

            event = json.loads(daily_path.read_text(encoding="utf-8"))
            self.assertEqual(event["ts"], "2026-06-24T10:11:12Z")
            self.assertEqual(event["params"]["token"], "***REDACTED***")

    def test_records_on_different_days_use_different_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = AuditLogger(str(Path(temp_dir) / "audit.jsonl"))

            for timestamp in ("2026-06-24T23:59:59Z", "2026-06-25T00:00:00Z"):
                with patch(
                    "ssh_assist_mcp.audit.time.gmtime",
                    return_value=time.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ"),
                ):
                    logger.record("ssh.run_command", "host", "low", {}, "success")

            self.assertTrue((Path(temp_dir) / "audit-2026-06-24.jsonl").exists())
            self.assertTrue((Path(temp_dir) / "audit-2026-06-25.jsonl").exists())

    def test_default_log_path_uses_user_runtime_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {}, clear=True), patch("ssh_assist_mcp.paths.Path.home", return_value=Path(temp_dir)):
                logger = AuditLogger()

            self.assertEqual(
                logger.path,
                Path(temp_dir) / "jumpserver-ssh-mcp" / "logs" / "jumpserver-ssh-mcp-audit.jsonl",
            )


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None

from ssh_assist_mcp import __version__


class PackagingMetadataTest(unittest.TestCase):
    def test_project_version_uses_package_attribute_as_single_source(self):
        if tomllib is None:
            self.skipTest("tomllib requires Python 3.11+")
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        self.assertEqual(__version__, "0.1.0")
        self.assertNotIn("version", pyproject["project"])
        self.assertEqual(pyproject["project"]["dynamic"], ["version"])
        self.assertEqual(
            pyproject["tool"]["setuptools"]["dynamic"]["version"],
            {"attr": "ssh_assist_mcp.__version__"},
        )


if __name__ == "__main__":
    unittest.main()

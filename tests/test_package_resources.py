import unittest
from importlib.resources import files

from ssh_assist_mcp.matchers import MatcherRegistry
from ssh_assist_mcp.server import matcher_guide_resource


class PackageResourcesTest(unittest.TestCase):
    def test_package_contains_runtime_matcher_docs(self):
        text = (files("ssh_assist_mcp") / "resources/docs/matchers/guide.md").read_text(encoding="utf-8")

        self.assertIn("Matcher", text)
        self.assertIn("ssh.matcher_probe", text)

    def test_package_contains_reference_matchers(self):
        text = (
            files("ssh_assist_mcp") / "resources/matchers/reference/ttyuyin-opt-account.json"
        ).read_text(encoding="utf-8")

        self.assertIn("ttyuyin-opt-account", text)

    def test_registry_loads_packaged_reference_matchers_without_search_path(self):
        registry = MatcherRegistry()

        self.assertIn("ttyuyin-opt-account", registry.list())
        self.assertIn("qmzy-asset-list-id", registry.list())

    def test_matcher_resource_reader_can_use_packaged_docs(self):
        text = matcher_guide_resource()

        self.assertIn("ssh.matcher_probe", text)


if __name__ == "__main__":
    unittest.main()

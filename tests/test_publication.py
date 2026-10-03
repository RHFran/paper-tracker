"""Repository publication contracts: branding, portable demos and safe defaults."""
import copy
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from literature_digest.config import load_configs
from literature_digest.demo import preview

ROOT = Path(__file__).resolve().parents[1]


class PublicationTest(unittest.TestCase):
    def test_preferred_and_legacy_cli_entry_points_are_identical(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        self.assertEqual(project["name"], "paper-tracker")
        self.assertEqual(project["scripts"]["paper-tracker"], "literature_digest.cli:main")
        self.assertEqual(project["scripts"]["literature-digest"], project["scripts"]["paper-tracker"])
        self.assertEqual(project["dependencies"], [])

    def test_bilingual_readmes_link_to_reproducible_examples(self):
        for filename in ("README.md", "README_中文.md"):
            text = (ROOT / filename).read_text()
            self.assertTrue(text.startswith("# Paper Tracker"))
            for language in ("en", "zh-CN"):
                for extension in ("html", "txt", "json"):
                    relative = f"examples/preview/demo.{language}.{extension}"
                    self.assertIn(f"]({relative})", text)
                    self.assertTrue((ROOT / relative).is_file())
            self.assertIn("paper-tracker", text)
            self.assertIn("literature-digest", text)

    def test_checked_in_demo_files_match_the_generator(self):
        config = load_configs(str(ROOT / "config.example.json"))[0]
        with tempfile.TemporaryDirectory() as directory:
            config = copy.deepcopy(config)
            config["output_dir"] = directory
            for language in ("en", "zh-CN"):
                result = preview(config, language)
                for extension, generated in result["paths"].items():
                    fixture = ROOT / "examples/preview" / f"demo.{language}.{extension}"
                    with self.subTest(language=language, extension=extension):
                        self.assertEqual(Path(generated).read_bytes(), fixture.read_bytes())
                text = Path(result["paths"]["html"]).read_text()
                self.assertIn("PAPER TRACKER", text)
                self.assertNotIn("<script", text.lower())
                self.assertNotIn("<img", text.lower())
                audit = json.loads(Path(result["paths"]["json"]).read_text())
                self.assertTrue(audit["meta"]["synthetic"])
                self.assertEqual(audit["meta"]["retrieved"], 0)
                self.assertNotIn("recipient", audit)

    def test_example_configs_keep_models_and_sending_disabled(self):
        for filename in ("config.example.json", "config.profiles.example.json",
                         "templates/profiles.example.json"):
            for profile in load_configs(str(ROOT / filename)):
                with self.subTest(file=filename, profile=profile["profile_id"]):
                    self.assertFalse(profile["mail"]["enabled"])
                    self.assertFalse(profile["llm"]["enabled"])
                    self.assertTrue(profile["recipient"].endswith("@example.org"))


if __name__ == "__main__":
    unittest.main()

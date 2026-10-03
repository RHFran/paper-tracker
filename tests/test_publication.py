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
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project["name"], "paper-tracker")
        self.assertEqual(project["scripts"]["paper-tracker"], "literature_digest.cli:main")
        self.assertEqual(project["scripts"]["literature-digest"], project["scripts"]["paper-tracker"])
        # Only native Windows needs the IANA timezone database package.
        self.assertEqual(project["dependencies"], ["Pillow>=11.0", "tzdata>=2024.1; sys_platform == 'win32'"])

    def test_bilingual_readmes_link_to_reproducible_examples(self):
        for filename, guide, setup in (("README.md", "user-guide.md", "platform-setup.md"),
                                       ("README_中文.md", "user-guide_中文.md", "platform-setup_中文.md")):
            text = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn('<h1 align="center">Super Paper radar</h1>', text)
            self.assertIn('src="docs/assets/logo.svg"', text)
            self.assertTrue((ROOT / "docs/assets/logo.svg").is_file())
            for relative in ("examples/preview/README.md", "docs/" + guide, "docs/" + setup):
                self.assertIn(f"]({relative})", text)
            self.assertIn("https://rhfran.github.io/super-paper-radar/", text)
            details = (ROOT / "docs" / guide).read_text(encoding="utf-8")
            for language in ("en", "zh-CN"):
                for extension in ("html", "txt", "json"):
                    relative = f"examples/preview/demo.{language}.{extension}"
                    self.assertIn(f"](../{relative})", details)
                    self.assertTrue((ROOT / relative).is_file())
                for extension in ("ris", "bib"):
                    self.assertTrue((ROOT / f"examples/preview/demo.{language}.{extension}").is_file())
            self.assertIn("paper-tracker", text)
            self.assertIn("literature-digest", details)
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README_中文.md").read_text(encoding="utf-8")
        self.assertEqual(english.split('<a id="中文说明"></a>\n\n', 1)[1], chinese)

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
                text = Path(result["paths"]["html"]).read_text(encoding="utf-8")
                self.assertIn("SUPER PAPER RADAR", text)
                self.assertNotIn("<script", text.lower())
                self.assertNotIn("<img", text.lower())
                audit = json.loads(Path(result["paths"]["json"]).read_text(encoding="utf-8"))
                self.assertTrue(audit["meta"]["synthetic"])
                self.assertEqual(audit["meta"]["retrieved"], 0)
                self.assertNotIn("recipient", audit)

    def test_example_configs_keep_models_and_sending_disabled(self):
        for filename in ("config.example.json", "config.profiles.example.json", "config.calendar.example.json",
                         "templates/profiles.example.json"):
            for profile in load_configs(str(ROOT / filename)):
                with self.subTest(file=filename, profile=profile["profile_id"]):
                    self.assertFalse(profile["mail"]["enabled"])
                    self.assertFalse(profile["llm"]["enabled"])
                    self.assertTrue(profile["recipient"].endswith("@example.org"))


if __name__ == "__main__":
    unittest.main()

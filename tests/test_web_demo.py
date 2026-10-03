"""Static public demo integrity; never calls a network service."""
import json
import re
import unittest
from xml.etree import ElementTree
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.local_paths = []
        self.input_types = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "input":
            self.input_types.append(attrs.get("type"))
        if tag == "script":
            self.scripts.append(attrs.get("src"))
        for key in ("href", "src"):
            value = attrs.get(key, "")
            if value and not value.startswith(("http:", "https:", "#", "mailto:")):
                self.local_paths.append(value)


class WebDemoTests(unittest.TestCase):
    def test_brand_assets_are_self_contained_and_accessible(self):
        for filename in ("logo.svg", "icon.svg", "favicon.svg"):
            with self.subTest(filename=filename):
                svg = (DOCS / "assets" / filename).read_text(encoding="utf-8")
                root = ElementTree.fromstring(svg)
                self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
                self.assertIn("viewBox", root.attrib)
                for forbidden in ("<script", "<foreignObject", "<image", "href=", "<text"):
                    self.assertNotIn(forbidden, svg)
        logo = ElementTree.parse(DOCS / "assets/logo.svg").getroot()
        self.assertEqual(logo.find("{http://www.w3.org/2000/svg}title").text,
                         "Super Paper radar")
        self.assertIsNotNone(logo.find("{http://www.w3.org/2000/svg}desc"))
        html = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertIn('aria-label="Super Paper radar home"', html)
        self.assertIn('src="assets/icon.svg"', html)
        self.assertIn("Super Paper radar", html)

    def test_renamed_repository_and_pages_links_are_consistent(self):
        for filename in ("README.md", "README_中文.md", "docs/index.html",
                         "docs/platform-setup.md", "docs/platform-setup_中文.md",
                         "docs/user-guide.md", "docs/user-guide_中文.md"):
            with self.subTest(filename=filename):
                text = (ROOT / filename).read_text(encoding="utf-8")
                self.assertNotIn("github.com/RHFran/paper-tracker", text)
                self.assertNotIn("github.com/RHFran/smart-paper-tracker", text)
                self.assertNotIn("rhfran.github.io/paper-tracker", text)
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn("github.repository == 'RHFran/super-paper-radar'", workflow)

    def test_local_assets_links_and_unique_ids(self):
        markup = Markup()
        markup.feed((DOCS / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(len(markup.ids), len(set(markup.ids)))
        for path in markup.local_paths:
            with self.subTest(path=path):
                self.assertTrue((DOCS / path).exists())
        script = (DOCS / "assets/app.js").read_text(encoding="utf-8")
        for identifier in re.findall(r"byId\('([^']+)'\)", script):
            self.assertIn(identifier, markup.ids)
        self.assertEqual(markup.input_types, ["time"])
        self.assertEqual(markup.scripts, ["assets/fixtures.js", "assets/app.js"])
        self.assertTrue((DOCS / ".nojekyll").exists())

    def test_public_samples_are_identical_to_audited_examples(self):
        for language in ("en", "zh-CN"):
            for extension in ("html", "json", "txt", "ris", "bib"):
                filename = f"demo.{language}.{extension}"
                with self.subTest(filename=filename):
                    self.assertEqual((DOCS / "preview" / filename).read_bytes(),
                                     (ROOT / "examples/preview" / filename).read_bytes())

    def test_javascript_fixture_is_identical_to_evidence_json(self):
        text = (DOCS / "assets/fixtures.js").read_text(encoding="utf-8")
        data = json.loads(text.split("window.PAPER_TRACKER_DEMO = ", 1)[1].rstrip(";\n"))
        for language, fixture in data.items():
            self.assertEqual(fixture, json.loads((DOCS / "preview" / f"demo.{language}.json").read_text(encoding="utf-8")))
            self.assertTrue(fixture["meta"]["synthetic"])
            self.assertEqual(fixture["meta"]["retrieved"], 0)
            for paper in fixture["papers"]:
                for claims in paper["analysis"]["fields"].values():
                    for claim in claims:
                        self.assertIn(claim["evidence"], paper["full_text"])

    def test_no_remote_services_or_collected_credentials(self):
        script = (DOCS / "assets/app.js").read_text(encoding="utf-8")
        for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "localStorage", "sessionStorage", "document.cookie"):
            self.assertNotIn(forbidden, script)
        html = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('<form', html)
        self.assertNotIn('type="password"', html)
        self.assertNotIn('type="email"', html)
        self.assertIn('data-i18n="demoNotice"', html)
        self.assertIn('data-i18n="costNotice"', html)
        self.assertIn('<noscript>', html)


if __name__ == "__main__":
    unittest.main()

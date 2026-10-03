"""Offline preview regression tests; no real research or external services."""
import copy
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from literature_digest import demo
from literature_digest.analysis import FIELDS, validate_analysis, validate_overview
from literature_digest.config import DEFAULTS
from literature_digest.perspective import validate_perspective
from literature_digest.outlook import checked_outlook


class DemoTest(unittest.TestCase):
    def config(self, directory):
        config = copy.deepcopy(DEFAULTS)
        config.update(output_dir=str(Path(directory) / "preview"),
                      state_path=str(Path(directory) / "state" / "digest.sqlite3"))
        return config

    def test_fixture_anchors_global_references_and_honest_metadata(self):
        for language in ("zh-CN", "en"):
            with self.subTest(language=language):
                papers = demo._papers(language)
                overview = demo._overview(papers, language)
                self.assertEqual(len(papers), 2)
                for paper in papers:
                    self.assertIn("DEMO", paper.title)
                    self.assertIn("SYNTHETIC", paper.title)
                    self.assertEqual(paper.doi, "")
                    self.assertTrue(paper.key.startswith("demo:"))
                    self.assertTrue(paper.url.startswith("https://example.org/demo/"))
                    self.assertTrue(paper.provenance[0]["synthetic"])
                    self.assertFalse(paper.provenance[0]["retrieved"])
                    self.assertEqual(paper.analysis["mode"], "synthetic_demo")
                    self.assertEqual(set(paper.analysis["fields"]), set(FIELDS))
                    self.assertTrue(all(paper.analysis["fields"].values()))
                    validate_analysis(paper.analysis["fields"], paper.evidence, language)
                    validate_perspective(paper.analysis["perspective"], paper.evidence, language)
                validate_overview({"paragraphs": overview["paragraphs"]}, papers, language)
                self.assertEqual([ref["number"] for ref in overview["references"]], [1, 2])
                first = overview["paragraphs"][0]["sentences"][0]
                self.assertEqual([c["ref"] for c in first["citations"]], [1, 2])

    def test_language_override_reaches_renderer_without_mutating_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(directory)
            before = copy.deepcopy(config)
            with patch.object(demo, "render", return_value=("DEMO text", "<html>DEMO</html>")) as renderer:
                result = demo.preview(config, "en")
            papers, meta, options, overview, outlook = renderer.call_args.args
            self.assertEqual(options["language"], "en")
            self.assertEqual(meta["language"], "en")
            self.assertEqual(overview["language"], "en")
            self.assertIsNotNone(checked_outlook(outlook,papers,'en',allow_synthetic=True))
            self.assertIsNone(checked_outlook(outlook,papers,'en'))
            self.assertTrue(all(p.analysis["language"] == "en" for p in papers))
            self.assertEqual(config, before)
            self.assertEqual(result["status"], "demo_preview")
            self.assertEqual(Path(result["paths"]["html"]).name, "demo.en.html")
            self.assertFalse(Path(config["state_path"]).parent.exists())

    def test_no_network_database_mail_or_model_even_if_enabled(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            config = self.config(directory)
            config["mail"]["enabled"] = True
            config["llm"]["enabled"] = True
            config["images"] = {"mode": "embed", "max_per_paper": 3}
            config["figure_catalog"] = {"demo:forest-bvoc": [{"url": "https://example.org/remote-image"}]}
            state_path = Path(config["state_path"])
            state_path.parent.mkdir()
            sentinel = b"not-a-database; must remain byte-for-byte unchanged"
            state_path.write_bytes(sentinel)
            for target in ("socket.create_connection", "socket.socket.connect", "sqlite3.connect",
                           "smtplib.SMTP", "smtplib.SMTP_SSL",
                           "literature_digest.http.HttpClient.__init__",
                           "literature_digest.analysis._model_request"):
                stack.enter_context(patch(target, side_effect=AssertionError("Demo attempted an external side effect")))
            result = demo.preview(config)
            self.assertFalse(result["network_used"])
            self.assertFalse(result["state_changed"])
            self.assertFalse(result["mail_sent"])
            self.assertEqual(state_path.read_bytes(), sentinel)
            self.assertEqual(result["paper_count"], 2)
            self.assertFalse(list(state_path.parent.glob("*.lock")))

    def test_outputs_are_idempotent_localized_and_auditable(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(directory)
            for language in ("zh-CN", "en"):
                result = demo.preview(config, language)
                initial = {extension: Path(path).read_bytes() for extension, path in result["paths"].items()}
                repeated = demo.preview(config, language)
                self.assertEqual(result, repeated)
                self.assertEqual(initial, {ext: Path(path).read_bytes() for ext, path in repeated["paths"].items()})
                self.assertEqual(set(initial), {"html", "txt", "json", "ris", "bib"})
                self.assertIn("DEMO", initial["html"].decode())
                self.assertIn("DEMO", initial["txt"].decode())
                self.assertIn('lang="' + language + '"', initial["html"].decode())
                self.assertIn(result["notice"], initial["txt"].decode())
                self.assertIn(result["notice"], initial["html"].decode())
                for label in (("问题与设计", "科学问题", "方法链", "结果与亮点", "局限性", "有何启发", "本期总结与研究启发") if language == "zh-CN"
                              else ("Problem and design", "Scientific question", "Method chain", "Results and highlights", "Limitations", "Research implications", "Closing synthesis and research outlook")):
                    self.assertIn(label, initial["txt"].decode())
                    self.assertIn(label, initial["html"].decode())
                audit = json.loads(initial["json"])
                self.assertTrue(audit["meta"]["demo"])
                self.assertTrue(audit["meta"]["synthetic"])
                self.assertEqual(audit["meta"]["retrieved"], 0)
                self.assertEqual(len(audit["papers"]), 2)
                self.assertIn('outlook',audit)
                self.assertNotIn("recipient", audit)
                for paper in audit["papers"]:
                    for items in paper["analysis"]["fields"].values():
                        for claim in items:
                            self.assertIn(claim["evidence"], paper["full_text"])
            self.assertEqual(len(list(Path(config["output_dir"]).iterdir())), 10)
            self.assertFalse(Path(config["state_path"]).exists())

    def test_unsupported_or_unsafe_language_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(directory)
            for language in ("fr", "../en", "en/../../state", "", 123):
                with self.subTest(language=language), self.assertRaises(ValueError):
                    demo.preview(config, language)
            self.assertFalse(Path(config["output_dir"]).exists())

    def test_failed_atomic_replace_preserves_original_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo.en.txt"
            target.write_text("original", encoding="utf-8")
            with patch.object(demo.os, "replace", side_effect=OSError("synthetic replace failure")):
                with self.assertRaises(OSError):
                    demo._atomic_write(target, "replacement")
            self.assertEqual(target.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(Path(directory).iterdir()), [target])


if __name__ == "__main__":
    unittest.main()

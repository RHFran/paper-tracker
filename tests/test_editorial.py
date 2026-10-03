"""Offline editorial tests. All study records and claims below are synthetic fixtures."""
import copy
import json
import os
import unittest
from unittest.mock import patch

from literature_digest.analysis import (FIELDS, analyze, compose_overview,
    reference_map, validate_analysis, validate_overview)
from literature_digest.models import Paper
from literature_digest.render import render, safe_image_url, safe_link

EVIDENCE_A = "Synthetic source A reports a controlled toy experiment with three simulated inputs."
EVIDENCE_B = "Synthetic source B evaluates a toy model on an artificial testing grid."
ANCHOR_A = "a controlled toy experiment with three simulated inputs"
ANCHOR_B = "a toy model on an artificial testing grid"


def fixture_paper(number=1, language="en", tracks=None, grounded=True):
    evidence, anchor = (EVIDENCE_A, ANCHOR_A) if number == 1 else (EVIDENCE_B, ANCHOR_B)
    p = Paper(title=f"Synthetic fixture {number}, not a real study", source_id=str(number),
              source="fixture", doi=f"10.9999/synthetic-{number}",
              url=f"https://doi.org/10.9999/synthetic-{number}", abstract=evidence,
              authors=["A. Synthetic", "B. Fixture"], journal="Synthetic test venue",
              publication_date="2026-10-02", tracks=tracks or ["custom"],
              evidence_level="摘要")
    claim = ("合成夹具报告了一项玩具实验。" if language.startswith("zh")
             else "The synthetic fixture describes a toy experiment." if number == 1
             else "The synthetic fixture evaluates a toy model.")
    fields = {key: [] for key in FIELDS}
    fields["highlights"] = [{"text": "合成夹具提供可核对的玩具示例。" if language.startswith("zh")
                            else "The synthetic fixture provides a toy example.", "evidence": anchor}]
    fields["findings"] = [{"text": claim, "evidence": anchor}]
    fields["question"] = [{"text": "合成夹具检验玩具输入。" if language.startswith("zh")
                          else "The synthetic fixture examines toy inputs.", "evidence": anchor}]
    p.analysis = {"mode": "llm_grounded" if grounded else "discovery_only", "language": language,
                  "fields": fields if grounded else {key: [] for key in FIELDS}}
    return p


def cfg(language="en"):
    return {"language": language, "topics": [{"id": "custom", "name": "Synthetic topic"}],
            "llm": {"enabled": False, "base_url_env": "TEST_EDITORIAL_BASE",
                    "api_key_env": "TEST_EDITORIAL_KEY", "model_env": "TEST_EDITORIAL_MODEL",
                    "max_evidence_chars": 60000}, "images": {"mode": "off"}}


META = {"local_date": "2026-10-03", "timezone": "Etc/UTC", "publication_start": "2026-09-26",
        "window_start": "2026-09-26T11:00:00Z", "window_end": "2026-10-03T11:00:00Z",
        "publication_window_days": 7, "retrieved": 3, "relevant": 2}


class FakeHttp:
    def __init__(self, result):
        self.result, self.calls = result, []
    def json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return {"choices": [{"message": {"content": json.dumps(self.result)}}]}


class AnalysisLanguageTests(unittest.TestCase):
    def test_english_chinese_and_arbitrary_language(self):
        for language, claim in [("en", "A synthetic toy experiment."), ("zh-CN", "合成玩具实验。"),
                                ("fr", "Une expérience synthétique.")]:
            data = {key: [] for key in FIELDS}
            data["methods"] = [{"text": claim, "evidence": ANCHOR_A}]
            self.assertEqual(validate_analysis(data, EVIDENCE_A, language)["methods"][0]["text"], claim)

    def test_editorial_schema_has_exact_four_blocks(self):
        self.assertEqual(set(FIELDS), {"highlights", "question", "methods", "findings"})

    def test_markup_cannot_forge_matching_anchor(self):
        data = {key: [] for key in FIELDS}
        data["methods"] = [{"text": "A synthetic test claim.",
                            "evidence": "a controlled <script></script>toy experiment with three simulated inputs"}]
        with self.assertRaises(ValueError):
            validate_analysis(data, EVIDENCE_A, "en")

    def test_no_claim_without_anchor_or_with_unknown_keys(self):
        data = {key: [] for key in FIELDS}
        data["findings"] = [{"text": "A synthetic claim.", "evidence": "Fabricated nonexistent quotation"}]
        with self.assertRaises(ValueError):
            validate_analysis(data, EVIDENCE_A, "en")
        data["findings"] = [{"text": "A synthetic claim.", "evidence": ANCHOR_A, "extra": "x"}]
        with self.assertRaises(ValueError):
            validate_analysis(data, EVIDENCE_A, "en")

    def test_model_prompt_uses_configured_language(self):
        p = fixture_paper()
        config = cfg("en"); config["llm"]["enabled"] = True
        http = FakeHttp(p.analysis["fields"])
        with patch.dict(os.environ, {"TEST_EDITORIAL_BASE": "https://model.example.org/v1",
                                    "TEST_EDITORIAL_KEY": "synthetic-token", "TEST_EDITORIAL_MODEL": "fixture"}):
            result = analyze(p, config, http)
        self.assertEqual(result["mode"], "llm_grounded")
        content = json.loads(http.calls[0][1]["payload"]["messages"][1]["content"])
        self.assertEqual(content["output_language"], "en")
        self.assertEqual(result["language"], "en")

    def test_truncation_cannot_cite_unseen_evidence(self):
        p = fixture_paper(); p.abstract = "An initial synthetic prefix. " * 12 + EVIDENCE_A
        config = cfg(); config["llm"].update(enabled=True, max_evidence_chars=100)
        http = FakeHttp(p.analysis["fields"])
        with patch.dict(os.environ, {"TEST_EDITORIAL_BASE": "https://model.example.org/v1",
                                    "TEST_EDITORIAL_KEY": "synthetic-token", "TEST_EDITORIAL_MODEL": "fixture"}):
            result = analyze(p, config, http)
        self.assertEqual(result["mode"], "discovery_only")


class OverviewTests(unittest.TestCase):
    def data(self):
        return {"paragraphs": [{"sentences": [{"text": "The synthetic studies examine toy experiments and models.",
                "citations": [{"ref": 1, "evidence": ANCHOR_A}, {"ref": 2, "evidence": ANCHOR_B}]}]}]}

    def test_valid_cross_paper_reference_map(self):
        a, b = fixture_paper(), fixture_paper(2)
        result = validate_overview(self.data(), [a, b], "en")
        self.assertEqual([c["ref"] for c in result[0]["sentences"][0]["citations"]], [1, 2])
        self.assertEqual(len(reference_map([a, b, a])), 2)

    def test_citation_must_match_its_paper(self):
        data = self.data(); data["paragraphs"][0]["sentences"][0]["citations"][0]["evidence"] = ANCHOR_B
        with self.assertRaises(ValueError):
            validate_overview(data, [fixture_paper(), fixture_paper(2)], "en")

    def test_missing_unknown_boolean_duplicate_citations_rejected(self):
        for citations in [[], [{"ref": 3, "evidence": ANCHOR_A}], [{"ref": True, "evidence": ANCHOR_A}],
                          [{"ref": 1, "evidence": ANCHOR_A}] * 2]:
            data = self.data(); data["paragraphs"][0]["sentences"][0]["citations"] = citations
            with self.assertRaises(ValueError):
                validate_overview(data, [fixture_paper(), fixture_paper(2)], "en")

    def test_unknown_input_quotation_rejected_even_if_in_source(self):
        with self.assertRaises(ValueError):
            validate_overview(self.data(), [fixture_paper(), fixture_paper(2)], "en", allowed_evidence={})

    def test_review_model_input_and_output(self):
        papers = [fixture_paper(), fixture_paper(2)]
        config = cfg(); config["llm"]["enabled"] = True
        http = FakeHttp(self.data())
        with patch.dict(os.environ, {"TEST_EDITORIAL_BASE": "https://model.example.org/v1",
                                    "TEST_EDITORIAL_KEY": "synthetic-token", "TEST_EDITORIAL_MODEL": "fixture"}):
            result = compose_overview(papers, config, http)
        self.assertEqual(result["mode"], "llm_grounded")
        self.assertEqual(result["references"], reference_map(papers))
        self.assertEqual(len(result["paragraphs"][0]["sentences"][0]["citations"]), 2)

    def test_failed_overview_keeps_verified_extracts(self):
        config = cfg(); config["llm"]["enabled"] = True
        result = compose_overview([fixture_paper()], config, FakeHttp({"paragraphs": []}))
        self.assertEqual(result["mode"], "grounded_extracts")
        self.assertTrue(result["warnings"])
        self.assertEqual(result["paragraphs"][0]["sentences"][0]["citations"][0]["evidence"], ANCHOR_A)

    def test_discovery_has_no_manufactured_review_claims(self):
        result = compose_overview([fixture_paper(grounded=False)], cfg(), None)
        self.assertEqual(result["mode"], "discovery_only")
        self.assertEqual(result["paragraphs"], [])


class RenderTests(unittest.TestCase):
    def test_real_html_english_and_omitted_empty_sections(self):
        text, html = render([fixture_paper()], META, cfg())
        self.assertIn('<html lang="en">', html)
        self.assertIn('<table role="presentation"', html)
        self.assertIn('<sup', html)
        self.assertNotIn('<pre', html)
        self.assertIn("Main results", text)
        self.assertNotIn("Author-reported limitations", text)
        self.assertNotIn("当前取得的来源", text)
        self.assertNotIn("阅读边界", text)
        self.assertIn('id="ref-1"', html)
        self.assertIn("References", text)

    def test_synthetic_paper_analysis_requires_demo_context(self):
        p = fixture_paper(); p.analysis["mode"] = "synthetic_demo"
        text, _ = render([p], META, cfg())
        self.assertNotIn("Main results", text)
        text, html = render([p], {**META, "demo": True, "title": "Fixture preview"}, cfg())
        self.assertIn("SYNTHETIC DEMO", text)
        self.assertIn("Main results", text)
        self.assertIn("Synthetic fixture text", text)
        self.assertNotIn("Abstract evidence", text)
        self.assertIn("<title>Fixture preview</title>", html)

    def test_demo_notice_and_fixture_stats_are_not_repeated_or_misleading(self):
        text, html = render([fixture_paper()], {**META, "demo": True,
            "demo_notice": "SYNTHETIC DEMO: fixture only.", "retrieved": 0, "fixture_count": 1}, cfg())
        self.assertEqual(text.count("SYNTHETIC DEMO:"), 1)
        self.assertEqual(html.count("SYNTHETIC DEMO:"), 1)
        self.assertIn("1 Demo records", text)

    def test_chinese_ui_and_custom_topic(self):
        config = cfg("zh-CN"); config["topics"][0]["name"] = "自定义主题"
        text, html = render([fixture_paper(language="zh-CN")], META, config)
        self.assertIn("自定义主题", text)
        self.assertIn("科学问题", text)
        self.assertIn('<html lang="zh-CN">', html)

    def test_global_numbering_across_overlapping_topics(self):
        a, b = fixture_paper(tracks=["custom", "second"]), fixture_paper(2, tracks=["second"])
        config = cfg(); config["topics"].append({"id": "second", "name": "Second topic"})
        text, html = render([a, b, a], META, config)
        self.assertEqual(html.count('id="ref-1"'), 1)
        self.assertEqual(html.count('id="ref-2"'), 1)
        self.assertNotIn('id="ref-3"', html)
        self.assertIn('[2] Synthetic fixture 2', text)

    def test_untrusted_title_claim_caption_and_url_escaped(self):
        p = fixture_paper()
        p.title = '<script>alert("x")</script>'
        p.analysis["fields"]["findings"][0]["text"] = '<img src=x onerror="boom"> A synthetic claim.'
        p.figures = [{"caption": '<script>bad</script>', "source_url": "javascript:alert(1)",
                      "url": 'https://pmc.ncbi.nlm.nih.gov/image.png" onerror="boom', "embed_allowed": True}]
        config = cfg(); config["images"]["mode"] = "embed"
        _, html = render([p], META, config)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img src=x', html)
        self.assertNotIn('javascript:', html)
        self.assertIn('&lt;script&gt;', html)

    def test_discovery_only_renders_abstract_and_links_once(self):
        text, html = render([fixture_paper(grounded=False)], META, cfg())
        self.assertIn(EVIDENCE_A, text)
        self.assertIn("Abstract (source text)", text)
        self.assertNotIn("Scientific question", text)
        self.assertEqual(text.count("Discovery record"), 1)
        self.assertIn('href="https://doi.org/10.9999/synthetic-1"', html)

    def test_invalid_overview_cannot_render_stale_or_fabricated_claim(self):
        p = fixture_paper()
        overview = {"references": [{"number": 1, "paper_key": "wrong"}],
                    "paragraphs": [{"sentences": [{"text": "Fabricated unsupported trend.",
                                      "citations": [{"ref": 1, "evidence": ANCHOR_A}]}]}]}
        text, _ = render([p], META, cfg(), overview)
        self.assertNotIn("Fabricated unsupported trend", text)

    def test_invalid_analysis_cannot_render_unsupported_claim(self):
        p = fixture_paper(); p.analysis["fields"]["findings"][0]["evidence"] = "A fabricated source quotation"
        text, _ = render([p], META, cfg())
        self.assertNotIn("The synthetic fixture describes", text)
        self.assertIn("Abstract (source text)", text)

    def test_empty_and_failure_reports(self):
        empty, _ = render([], META, cfg())
        self.assertIn("No new papers matched", empty)
        failure, html = render([], {**META, "failure": True, "errors": ["Synthetic failure"]}, cfg())
        self.assertIn("availability is unknown", failure)
        self.assertNotIn("No new papers matched", failure)
        self.assertIn("Synthetic failure", html)


class FigureSafetyTests(unittest.TestCase):
    def figure(self, **kwargs):
        return {"caption": "Synthetic fixture figure, not research imagery", "url": "https://cdn.ncbi.nlm.nih.gov/fixture.png",
                "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC000000/", "license": "CC BY 4.0",
                "attribution": "Synthetic test authors", "license_scope": "figure", "embed_allowed": True, **kwargs}

    def test_only_trusted_public_https_image_hosts(self):
        self.assertTrue(safe_image_url("https://cdn.ncbi.nlm.nih.gov/figure.png"))
        for value in ["http://cdn.ncbi.nlm.nih.gov/figure.png", "https://127.0.0.1/x", "https://[::1]/x",
                      "https://192.168.1.1/x", "https://cdn.ncbi.nlm.nih.gov.attacker.org/x",
                      "https://cdn.ncbi.nlm.nih.gov@attacker.org/x", "https://cdn.ncbi.nlm.nih.gov:888/x",
                      "https://localhost/x", "https://user:secret@cdn.ncbi.nlm.nih.gov/x", "data:image/png;base64,x",
                      "https://cdn.ncbi.nlm.nih.gov\\@attacker.org/x", "https://cdn.ncbi.nlm.nih.gov/\nx"]:
            self.assertEqual(safe_image_url(value), "", value)

    def test_links_default_and_off(self):
        p = fixture_paper(); p.figures = [self.figure()]
        config = cfg(); config["images"]["mode"] = "links"
        text, html = render([p], META, config)
        self.assertIn("View original figure", html)
        self.assertNotIn('<img ', html)
        config["images"]["mode"] = "off"
        text, html = render([p], META, config)
        self.assertNotIn("Synthetic fixture figure", text)
        self.assertNotIn('<img ', html)

    def test_embedding_needs_permission_and_safe_host(self):
        p = fixture_paper(); config = cfg(); config["images"]["mode"] = "embed"
        for figure, expected in [(self.figure(), True), (self.figure(embed_allowed=False), False),
                                 (self.figure(embed_allowed="true"), False),
                                 (self.figure(url="https://untrusted.example.org/x.png"), False)]:
            p.figures = [figure]
            text, html = render([p], META, config)
            self.assertEqual('<img src=' in html, expected)
            self.assertIn("Synthetic test authors", text)

    def test_embedding_rechecks_figure_level_rights(self):
        p = fixture_paper(); config = cfg(); config["images"]["mode"] = "embed"
        for changed in [{"license_scope": "article"}, {"license_scope": None}, {"attribution": ""},
                        {"license": "CC BY-NC 4.0"}, {"license": "All rights reserved"}, {"license": 3},
                        {"source_url": "javascript:alert(1)"}]:
            p.figures = [self.figure(**changed)]
            _, html = render([p], META, config)
            self.assertNotIn('<img src=', html)

    def test_url_safety(self):
        for url in ["javascript:alert(1)", "https://localhost/a", "http://10.0.0.1/a", "https://u:p@example.org/a", "https://[bad"]:
            self.assertEqual(safe_link(url), "")
        self.assertEqual(safe_link("https://doi.org/10.1/test"), "https://doi.org/10.1/test")


if __name__ == "__main__":
    unittest.main()

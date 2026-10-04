"""Offline regression tests for visible, untrusted research coverage disclosures."""
from html import escape
from html.parser import HTMLParser
import unittest

from literature_digest.models import Paper
from literature_digest.render import render


class ParsedHTML(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


class CoverageRenderingTests(unittest.TestCase):
    def setUp(self):
        self.meta = {"local_date": "2026-10-04", "timezone": "UTC", "retrieved": 1}
        self.config = {"language": "en", "topics": []}
        self.paper = Paper(title="Synthetic test record", source="fixture", source_id="coverage-test",
                           url="https://example.org/paper")

    def test_exact_disclosure_once_before_results_for_all_result_states(self):
        notes = ("Synthetic source import failed; matching-paper availability remains unknown.\n"
                 "Verified primary source: https://example.org/paper?first=1&second=2\n\n"
                 "This bounded search is not an exhaustive bibliography.")
        for papers, flags in (([], {}), ([self.paper], {}), ([], {"partial_coverage": True}),
                              ([self.paper], {"partial_coverage": True}),
                              ([], {"failure": True, "errors": ["Synthetic import error"]})):
            with self.subTest(papers=bool(papers), flags=flags):
                text, html = render(papers, {**self.meta, **flags, "coverage_notes": notes}, self.config)
                self.assertEqual(text.count(notes), 1)
                self.assertIn("Search coverage and limitations\n" + notes + "\n", text)
                self.assertEqual(html.count(escape(notes).replace("\n", "<br />")), 1)
                self.assertLess(text.index(notes), text.index("Scope and methods:"))
                self.assertNotIn("<pre", html)

    def test_chinese_disclosure_heading_and_exact_text(self):
        notes = "来源导入失败，不能据此判断没有新论文。\n已核验原文：https://example.org/论文"
        text, html = render([], {**self.meta, "coverage_notes": notes}, {**self.config, "language": "zh-CN"})
        self.assertIn("检索覆盖与局限\n" + notes, text)
        self.assertIn("检索覆盖与局限</h2>", html)
        self.assertIn(escape(notes).replace("\n", "<br />"), html)

    def test_markup_and_unsafe_urls_remain_inert_literal_text(self):
        notes = ('</p></td></tr><script>alert("x")</script>\n'
                 '<img src=x onerror="alert(1)"> <a href="javascript:alert(1)">click</a>\n'
                 '<iframe src="https://example.org/"></iframe> & "quoted"\n'
                 'javascript:alert(1) data:text/html,<svg onload=alert(1)>')
        text, html = render([], {**self.meta, "coverage_notes": notes}, self.config)
        self.assertIn(notes, text)
        self.assertIn(escape(notes).replace("\n", "<br />"), html)
        parsed = ParsedHTML(html)
        self.assertFalse({tag for tag, _ in parsed.tags} & {"script", "img", "a", "iframe", "svg"})
        self.assertFalse(any(key.startswith("on") for _, attrs in parsed.tags for key in attrs))
        self.assertIn(notes.replace("\n", ""), "".join(parsed.text))

    def test_primary_urls_are_visible_without_new_autolinking(self):
        notes = "Verified primary URLs:\nhttps://doi.org/10.9999/synthetic\nhttps://example.org/paper?a=1&b=2"
        text, html = render([], {**self.meta, "coverage_notes": notes}, self.config)
        parsed = ParsedHTML(html)
        for url in notes.splitlines()[1:]:
            self.assertIn(url, text)
            self.assertIn(url, "".join(parsed.text))
        self.assertNotIn("<a ", html)

    def test_blank_and_nontext_notes_preserve_legacy_output_exactly(self):
        for papers, flags in (([], {}), ([self.paper], {}), ([], {"partial_coverage": True}),
                              ([], {"failure": True}), ([], {"demo": True})):
            meta = {**self.meta, **flags}
            expected = render(papers, meta, self.config)
            self.assertNotIn("Search coverage and limitations", expected[0])
            for notes in (None, "", " \n\t", [], {}, 1, True):
                with self.subTest(papers=bool(papers), flags=flags, notes=notes):
                    self.assertEqual(render(papers, {**meta, "coverage_notes": notes}, self.config), expected)

    def test_plain_text_preserves_whitespace_html_preserves_line_breaks(self):
        notes = "  First source unavailable.\r\nSecond source incomplete.\rThird source checked.\n "
        text, html = render([], {**self.meta, "coverage_notes": notes}, self.config)
        self.assertIn(notes, text)
        self.assertIn("  First source unavailable.<br />Second source incomplete.<br />Third source checked.<br /> ", html)

    def test_partial_empty_topic_does_not_claim_no_new_papers(self):
        self.paper.tracks = ["included"]
        topics = [{"id": "included", "name": "Included topic"}, {"id": "tree", "name": "Tree topic"}]
        for language, legacy, with_notes, without_notes in (
                ("zh-CN", "本期无新增论文。", "本期该主题未纳入正文论文；检索覆盖与局限见上方说明。",
                 "本次有限检索中，该主题未纳入正文论文，不能据此判断没有新增论文。"),
                ("en", "No new papers in this topic.",
                 "No papers from this topic were included in this issue; see the search coverage and limitations above.",
                 "No papers from this topic were included in this bounded retrieval; this does not establish that no new papers exist.")):
            config = {**self.config, "language": language, "topics": topics}
            for notes in ("Verified tree lead could not be imported: https://example.org/tree", None, "", " \n", []):
                with self.subTest(language=language, notes=notes):
                    meta = {**self.meta, "partial_coverage": True, "coverage_notes": notes}
                    expected = with_notes if isinstance(notes, str) and notes.strip() else without_notes
                    text, html = render([self.paper], meta, config)
                    self.assertIn(expected, text)
                    self.assertIn(expected, html)
                    self.assertNotIn(legacy, text)
                    self.assertNotIn(legacy, html)
                    if expected == with_notes:
                        self.assertLess(text.index(notes), text.index(expected))

    def test_nonpartial_empty_topic_preserves_legacy_wording(self):
        self.paper.tracks = ["included"]
        topics = [{"id": "included", "name": "Included topic"}, {"id": "tree", "name": "Tree topic"}]
        for language, legacy in (("zh-CN", "本期无新增论文。"), ("en", "No new papers in this topic.")):
            for notes in (None, "A synthetic source coverage note."):
                with self.subTest(language=language, notes=notes):
                    text, html = render([self.paper], {**self.meta, "coverage_notes": notes},
                                        {**self.config, "language": language, "topics": topics})
                    self.assertEqual(text.count(legacy), 1)
                    self.assertEqual(html.count(legacy), 1)


if __name__ == "__main__":
    unittest.main()

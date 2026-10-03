"""Offline fixtures for official arXiv body retrieval, never curated papers."""
import unittest

from literature_digest.http import RetrievalError
from literature_digest.models import Paper
from literature_digest.sources import enrich_full_text, fetch_arxiv


PROSE = (
    "We evaluate a synthetic retrieval system using independent held-out examples. "
    "The experiment compares the proposed method with a fixed reference method. "
    "The observations support the stated result within the tested conditions. "
    "These fixtures are invented for software tests and are not research findings. "
) * 3


def article(content=None):
    return ('<!doctype html><html><head><title>Metadata title</title></head><body>'
            '<nav>Outside navigation</nav><article class="ltx_document">'
            '<h1 class="ltx_title_document">Document title</h1>'
            '<div class="ltx_abstract"><p>Abstract only. ' + PROSE + '</p></div>'
            + (content if content is not None else '<section class="ltx_section"><h2>Methods</h2><p class="ltx_p">' + PROSE + '</p></section>')
            + '</article><footer>Outside footer</footer></body></html>').encode()


def paper(identifier="2610.01234v2", **kwargs):
    return Paper(title="Synthetic research", source="arxiv", source_id=identifier,
                 url="https://arxiv.org/abs/" + identifier,
                 abstract="An existing source abstract.", **kwargs)


class FakeHttp:
    def __init__(self, result):
        self.result, self.calls = result, []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ArxivFullTextTests(unittest.TestCase):
    def test_official_versioned_html_and_provenance(self):
        p, http = paper(), FakeHttp(article())
        enrich_full_text(p, http, {"fetch_full_text": True})
        self.assertEqual(http.calls[0][0][0], "https://arxiv.org/html/2610.01234v2")
        self.assertEqual(http.calls[0][1]["headers"]["Accept"], "text/html")
        self.assertEqual(http.calls[0][1]["interval"], 3.0)
        self.assertIn(PROSE.strip(), p.full_text)
        self.assertEqual(p.full_text_url, http.calls[0][0][0])
        self.assertIn("arXiv HTML", p.evidence_level)
        self.assertEqual(p.provenance[-1]["version_id"], "2610.01234v2")
        self.assertEqual(p.provenance[-1]["source"], "arxiv_fulltext")
        self.assertEqual(p.provenance[-1]["extracted_characters"], len(p.full_text))
        self.assertFalse(p.warnings)

    def test_strip_chrome_metadata_scripts_and_keep_tables(self):
        content = '''<div class="ltx_authors"><p>Author metadata</p></div>
        <nav>Inside navigation</nav><footer>Inside footer</footer>
        <script>function fakeEvidence() { return "Fabricated script result"; }</script>
        <style>.hidden { content: "Style contamination" }</style>
        <div hidden><p>Hidden metadata</p></div>
        <div aria-hidden="true">More hidden metadata</div>
        <section class="ltx_section"><p>''' + PROSE + '''</p>
        <p>Statistical comparison: p &lt; 0.05 and x &gt; 2; multi<span>-</span>agent.</p>
        <table><caption>Measured outcomes</caption><tr><th>Method</th><th>Score</th></tr>
        <tr><td>Reference</td><td>42</td></tr></table>
        <figure><img src="not-fetched.png"><figcaption>Measured figure caption</figcaption></figure>
        </section><section class="ltx_bibliography"><p>Reference metadata</p></section>'''
        p, http = paper(), FakeHttp(article(content))
        enrich_full_text(p, http)
        self.assertIn("Method Score Reference 42", p.full_text)
        self.assertIn("p < 0.05 and x > 2; multi-agent.", p.full_text)
        self.assertIn("Measured figure caption", p.full_text)
        for excluded in ("navigation", "footer", "metadata", "Document title", "Abstract only", "fakeEvidence", "Style contamination"):
            self.assertNotIn(excluded, p.full_text)
        self.assertEqual(len(http.calls), 1)

    def test_metadata_error_abstract_tables_and_short_body_never_fulltext(self):
        responses = [
            b"<html><body><h1>Access denied</h1></body></html>",
            ("<html><body><p>" + PROSE + "</p></body></html>").encode(),
            article(""),
            article('<section class="ltx_bibliography"><p>' + PROSE + '</p></section>'),
            article('<table><tr><td><p>' + PROSE + '</p></td></tr></table>'),
            article('<figure><figcaption><p>' + PROSE + '</p></figcaption></figure>'),
            article('<section class="ltx_section"><p>Too short.</p></section>'),
            b'<feed xmlns="http://www.w3.org/2005/Atom"><summary>Metadata</summary></feed>',
            article().replace(b'</article>', b''),
            article() + article(),
            b'\xff\xfe' + article(),
        ]
        for response in responses:
            with self.subTest(response=response[:60]):
                p = paper()
                enrich_full_text(p, FakeHttp(response))
                self.assertFalse(p.full_text)
                self.assertFalse(p.full_text_url)
                self.assertEqual(p.evidence, p.abstract)
                self.assertEqual(p.evidence_level, "仅摘要")
                self.assertTrue(p.warnings)
                self.assertFalse(p.provenance)

    def test_http_errors_preserve_abstract_and_existing_body(self):
        for failure in ("HTTP 404", "HTTP 429", "timeout", "API redirect denied"):
            with self.subTest(failure=failure):
                p = paper()
                enrich_full_text(p, FakeHttp(RetrievalError(failure)))
                self.assertEqual(p.evidence_level, "仅摘要")
                self.assertEqual(p.evidence, p.abstract)
                self.assertFalse(p.provenance)
        p = paper(full_text="Previously verified body", full_text_url="https://arxiv.org/html/2610.01234v1", evidence_level="Existing full text")
        enrich_full_text(p, FakeHttp(RetrievalError("HTTP 404")))
        self.assertEqual(p.full_text, "Previously verified body")
        self.assertEqual(p.evidence_level, "Existing full text")

    def test_no_abstract_means_metadata_fallback(self):
        p = paper()
        p.abstract = ""
        enrich_full_text(p, FakeHttp(RetrievalError("HTTP 404")))
        self.assertEqual(p.evidence_level, "仅元数据")

    def test_fetch_disabled_and_invalid_identity_do_not_request(self):
        for p, cfg in ((paper(), {"fetch_full_text": False, "images": {"mode": "links"}}),
                       (paper("https://evil.example/2610.01234v1"), {}),
                       (paper("../../private-file"), {})):
            with self.subTest(identifier=p.source_id):
                http = FakeHttp(article())
                enrich_full_text(p, http, cfg)
                self.assertEqual(http.calls, [])
                self.assertFalse(p.full_text)

    def test_legacy_identifier_and_unversioned_id(self):
        for identifier in ("hep-th/9901001v12", "2610.01234"):
            with self.subTest(identifier=identifier):
                p, http = paper(identifier), FakeHttp(article())
                enrich_full_text(p, http)
                self.assertEqual(http.calls[0][0][0], "https://arxiv.org/html/" + identifier)
                self.assertTrue(p.full_text)

    def test_merged_sources_preserve_known_latest_matching_version(self):
        p = Paper(title="Synthetic", source="crossref", source_id="10.48550/arxiv.2610.01234",
                  doi="10.48550/arxiv.2610.01234", url="https://evil.example/arbitrary",
                  arxiv_id="2610.01234", provenance=[
                      {"source": "arxiv", "version_id": "2610.01234v2"},
                      {"source": "arxiv", "version_id": "2610.01234v10"},
                      {"source": "arxiv", "version_id": "2610.09999v100"},
                      {"source": "crossref", "version_id": "2610.01234v200"}])
        http = FakeHttp(article())
        enrich_full_text(p, http)
        self.assertEqual(http.calls[0][0][0], "https://arxiv.org/html/2610.01234v10")


class ArxivLiteralQueryTests(unittest.TestCase):
    def run_query(self, value):
        http = FakeHttp(b'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/">'
                        b'<o:totalResults>0</o:totalResults><o:startIndex>0</o:startIndex></feed>')
        cfg = {"topics": [{"id": "test", "queries": [value]}], "max_pages_per_query": 1, "page_size": 5}
        fetch_arxiv(http, cfg, "2026-01-01", "2026-10-03", True)
        return http.calls[0][1]["params"]["search_query"]

    def test_natural_terms_need_not_be_one_exact_phrase(self):
        query = self.run_query("Earth system agent")
        self.assertTrue(query.startswith('(all:"Earth" AND all:"system" AND all:"agent")'))
        self.assertIn("submittedDate:[202601010000 TO 202610032359]", query)

    def test_provider_syntax_cannot_change_scope_or_dates(self):
        query = self.run_query('agent") OR submittedDate:[1900 TO 2100]')
        self.assertIn('all:"OR"', query)
        self.assertIn('all:"submittedDate"', query)
        self.assertNotIn(' OR submittedDate:', query)
        self.assertEqual(query.count('submittedDate:['), 1)

    def test_unicode_tokens_and_empty_rejection(self):
        self.assertIn('all:"气候" AND all:"智能体"', self.run_query("气候 智能体"))
        with self.assertRaises(ValueError):
            self.run_query('"()[]:*')


if __name__ == "__main__":
    unittest.main()

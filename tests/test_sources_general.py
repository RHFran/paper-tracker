"""Offline synthetic fixtures for generic topics, identity, dates and image rights."""
import copy
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from literature_digest.config import DEFAULTS
from literature_digest.http import RetrievalError
from literature_digest.models import Paper, normalize_arxiv_id, parse_date_parts
from literature_digest.relevance import classify, literal_phrase_in, merge_papers
from literature_digest.sources import (
    ATOM, arxiv_paper, attach_figures, crossref_paper, enrich_full_text,
    fetch_arxiv, fetch_crossref, fetch_europepmc, safe_figure_url,
)


def paper(title="Quantum computing", **kwargs):
    return Paper(title=title, source="crossref", source_id="test", url="https://example.org/article", **kwargs)


def config():
    c = copy.deepcopy(DEFAULTS)
    c.update(topics=[{"id": "quantum", "name": "Quantum", "queries": ["quantum computing"], "include_any": ["quantum"]}],
             images={"mode": "links", "max_per_paper": 3}, figure_catalog={})
    return c


def entry(identifier="2610.01234v2", published="2026-10-01T23:30:00Z", updated="2026-10-02T23:30:00Z", doi="10.9999/journal"):
    return f'''<entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
    <id>http://arxiv.org/abs/{identifier}</id><title>Quantum computing</title>
    <summary>A synthetic abstract for tests.</summary><published>{published}</published><updated>{updated}</updated>
    <author><name>Test Author</name></author><arxiv:doi>{doi}</arxiv:doi></entry>'''


def feed(entries="", total=0, offset=0):
    return f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/">
    <o:totalResults>{total}</o:totalResults><o:startIndex>{offset}</o:startIndex>{entries}</feed>'''.encode()


class FakeHttp:
    def __init__(self, *responses):
        self.responses, self.calls = iter(responses), []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return next(self.responses)
    json = request


class GenericTopicTests(unittest.TestCase):
    def test_include_any_all_exclude(self):
        topics = [{"id": "econ", "queries": ["inflation"], "include_any": ["inflation", "interest rate"],
                   "include_all": ["monetary policy"], "exclude_any": ["simulation only"]}]
        self.assertEqual(classify(paper("Inflation and monetary-policy evidence"), topics), ["econ"])
        self.assertEqual(classify(paper("Inflation without required context"), topics), [])
        self.assertEqual(classify(paper("Inflation monetary policy simulation only"), topics), [])

    def test_queries_are_fallback_relevance(self):
        self.assertEqual(classify(paper(), [{"id": "q", "queries": ["quantum computing"]}]), ["q"])
        self.assertEqual(classify(paper(), [{"id": "q", "queries": ["orchids"]}]), [])

    def test_unicode_phrase_matching(self):
        self.assertTrue(literal_phrase_in("量子计算", "新的量子计算研究"))
        self.assertTrue(literal_phrase_in("café", "Evidence from CAFE\u0301 economics"))
        self.assertTrue(literal_phrase_in("quantum computing", "Quantum–computing results"))
        self.assertFalse(literal_phrase_in("cat", "catalysis"))

    def test_regular_expressions_remain_literal(self):
        self.assertFalse(literal_phrase_in(".*", "anything"))
        self.assertFalse(literal_phrase_in("(a+)+$", "aaaaaaaa"))
        self.assertTrue(literal_phrase_in("C++", "Analysis of C++ methods"))

    def test_crossref_custom_queries_replace_legacy(self):
        http = FakeHttp({"message": {"items": []}})
        _, report = fetch_crossref(http, config(), "2026-10-01", "2026-10-02", True)
        self.assertEqual(http.calls[0][1]["params"]["query"], "quantum computing")
        self.assertEqual(len(report["queries"]), 1)

    def test_source_override_cannot_inject_epmc_query(self):
        c = config()
        c["topics"][0]["source_queries"] = {"europepmc": ['quantum") OR FIRST_PDATE:[1900 TO 2100] OR ("']}
        http = FakeHttp({"hitCount": 0, "resultList": {"result": []}})
        fetch_europepmc(http, c, "2026-10-01", "2026-10-02", True)
        query = http.calls[0][1]["params"]["query"]
        self.assertEqual(query.count('"'), 2)
        self.assertEqual(query.count("FIRST_PDATE:["), 1)
        self.assertIn('TITLE_ABS:"quantum OR FIRST PDATE 1900 TO 2100 OR"', query)

    def test_invalid_date_window_rejected_before_http(self):
        with self.assertRaises(ValueError):
            fetch_arxiv(FakeHttp(), config(), "2026-10-02", "2026-10-01", True)


class IdentityTests(unittest.TestCase):
    def test_arxiv_version_normalization(self):
        self.assertEqual(normalize_arxiv_id("https://arxiv.org/pdf/2610.01234v3.pdf"), "2610.01234")
        self.assertEqual(normalize_arxiv_id("arXiv:hep-th/9901001v12"), "hep-th/9901001")
        self.assertEqual(normalize_arxiv_id("10.48550/arXiv.2610.01234"), "2610.01234")
        self.assertEqual(normalize_arxiv_id("https://evil.org/abs/2610.01234"), "")

    def test_arxiv_versions_dedupe_without_journal_doi(self):
        a, b = [arxiv_paper(ET.fromstring(entry(identifier=f"2610.01234v{v}")), {}) for v in (1, 2)]
        journal = paper(doi="10.9999/journal")
        result = merge_papers([a, b, journal], config()["topics"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].doi, "")
        self.assertNotIn("doi:10.9999/journal", result[0].aliases)
        self.assertEqual(result[0].relations[0]["id"], "10.9999/journal")
        self.assertEqual(len(result[0].provenance), 2)

    def test_preprint_journal_relations_are_not_identity(self):
        a = crossref_paper({"title": ["Test"], "DOI": "10.9999/pre", "type": "posted-content", "relation": {
            "is-preprint-of": [{"id-type": "doi", "id": "10.9999/final"}]}}, {})
        b = crossref_paper({"title": ["Test"], "DOI": "10.9999/final"}, {})
        self.assertEqual(len(merge_papers([a, b])), 2)
        self.assertEqual(a.relations[0]["type"], "is-preprint-of")

    def test_explicit_identity_equivalence_merges_and_retains_dates(self):
        a = crossref_paper({"title": ["Test"], "DOI": "10.9999/a", "published-online": {"date-parts": [[2026, 10, 1]]}, "relation": {
            "is-identical-to": [{"id-type": "doi", "id": "https://doi.org/10.9999/B"}]}}, {})
        b = crossref_paper({"title": ["Test"], "DOI": "10.9999/b", "published-online": {"date-parts": [[2026, 10, 2]]}}, {})
        result = merge_papers([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].provenance), 2)
        self.assertIn("doi:10.9999/b", result[0].aliases)

    def test_pmcid_bridges_sources(self):
        a = paper(doi="10.9999/a", pmcid="PMC42")
        b = Paper(title="Test", source="europepmc", source_id="PMC:PMC42", url="https://europepmc.org/articles/PMC42", pmcid="pmc42")
        self.assertEqual(len(merge_papers([a, b])), 1)

    def test_arxiv_doi_bridges_same_preprint(self):
        a = arxiv_paper(ET.fromstring(entry()), {})
        b = crossref_paper({"title": ["Test"], "DOI": "10.48550/arXiv.2610.01234"}, {})
        self.assertEqual(len(merge_papers([a, b])), 1)


class ArxivTests(unittest.TestCase):
    def test_original_submitted_date_not_updated_date(self):
        p = arxiv_paper(ET.fromstring(entry()), {})
        self.assertEqual(p.publication_date, "2026-10-01")
        self.assertEqual(p.provenance[0]["date_fields"]["arxiv-published"], "2026-10-01")
        self.assertIn("首次", p.publication_date_label)
        self.assertIn("预印本", p.kind)

    def test_invalid_and_partial_dates_are_not_evidence(self):
        for value in ("2026-02-31T00:00:00Z", "2026-10-01", "2026-10-01T00:00:00", ""):
            with self.subTest(value=value):
                p = arxiv_paper(ET.fromstring(entry(published=value)), {})
                self.assertEqual(p.publication_date, "")
                self.assertNotIn("arxiv-published", p.provenance[0]["date_fields"])
                self.assertTrue(p.warnings)

    def test_timestamp_normalized_utc(self):
        p = arxiv_paper(ET.fromstring(entry(published="2026-10-01T23:30:00-04:00")), {})
        self.assertEqual(p.publication_date, "2026-10-02")

    def test_atom_pagination_and_rate_limit(self):
        c = config(); c["page_size"] = 1
        http = FakeHttp(feed(entry(), total=2), feed(entry(identifier="2610.01235v1"), total=2, offset=1))
        papers, report = fetch_arxiv(http, c, "2026-10-01", "2026-10-02", True)
        self.assertEqual(len(papers), 2)
        self.assertTrue(report["complete"])
        self.assertEqual(http.calls[1][1]["params"]["start"], 1)
        self.assertEqual(http.calls[0][1]["interval"], 3.0)
        self.assertIn("submittedDate:[202610010000 TO 202610022359]", http.calls[0][1]["params"]["search_query"])

    def test_invalid_atom_or_incomplete_response_fails(self):
        for response in (b"not xml", b"<html/>", feed(total=1), feed(entry(), total=1, offset=4)):
            with self.subTest(response=response), self.assertRaises(RetrievalError):
                fetch_arxiv(FakeHttp(response), config(), "2026-10-01", "2026-10-02", True)

    def test_repeated_page_fails(self):
        c = config(); c["page_size"] = 1
        with self.assertRaises(RetrievalError):
            fetch_arxiv(FakeHttp(feed(entry(), 2), feed(entry(), 2, 1)), c, "2026-10-01", "2026-10-02", True)

    def test_crossref_posted_date_retained(self):
        p = crossref_paper({"title": ["Test"], "type": "posted-content", "posted": {"date-parts": [[2026, 10, 1]]}}, {})
        self.assertEqual(p.publication_date, "2026-10-01")
        self.assertIn("posted", p.provenance[0]["date_fields"])

    def test_malformed_partial_dates_rejected(self):
        for parts in ({"date-parts": []}, {"date-parts": [[2026, 13]]}, {"date-parts": [[0]]}, {"date-parts": [[True]]}, {"date-parts": [[2026, 10.8, 1]]}, []):
            self.assertEqual(parse_date_parts(parts), "")


class FigureTests(unittest.TestCase):
    def item(self, **kwargs):
        return {"caption": "Observed result", "url": "https://cdn.example.org/figure.png", "source_url": "https://example.org/article#f1",
                "license": "CC BY 4.0", "license_scope": "figure", "attribution": "Test Author, Test Study", **kwargs}

    def test_catalog_link_default_no_embedding(self):
        p, c = paper(), config()
        c["figure_catalog"] = {p.key: [self.item()]}
        attach_figures(p, c)
        self.assertEqual(len(p.figures), 1)
        self.assertFalse(p.figures[0]["embed_allowed"])
        self.assertEqual(p.figures[0]["provenance"]["source"], "configured_figure_catalog")

    def test_embedding_needs_figure_license_attribution_and_safe_asset(self):
        for changes, expected in (({}, True), ({"license": "CC0"}, True), ({"license": "CC BY-NC 4.0"}, False),
                                  ({"license_scope": "article"}, False), ({"license_scope": "unknown"}, False),
                                  ({"attribution": ""}, False), ({"url": "javascript:alert(1)"}, False),
                                  ({"license": "unknown", "embed_allowed": True}, False)):
            with self.subTest(changes=changes):
                p, c = paper(), config(); c["images"]["mode"] = "embed"
                c["figure_catalog"] = {p.key: [self.item(**changes)]}
                attach_figures(p, c)
                self.assertEqual(p.figures[0]["embed_allowed"], expected)

    def test_unsafe_url_sources_blocked(self):
        for url in ("http://example.org/a", "javascript:alert(1)", "file:///tmp/p", "https://127.0.0.1/a", "https://[::1]/a",
                    "https://10.0.0.2/a", "https://localhost/a", "https://0x7f.0.0.1/a", "https://127.1/a",
                    "https://example.local/a", "https://user:pass@example.org/a", "https://example.org:8080/a", "https://example.org\\@localhost/a"):
            with self.subTest(url=url):
                self.assertEqual(safe_figure_url(url), "")
        p, c = paper(), config(); c["figure_catalog"] = {p.key: [self.item(source_url="https://127.0.0.1/a")]}
        attach_figures(p, c)
        self.assertEqual(p.figures, [])
        self.assertTrue(p.warnings)

    def test_off_clears_figures_and_limit_is_idempotent(self):
        p, c = paper(), config(); c["figure_catalog"] = {p.key: [self.item(), self.item(url="https://cdn.example.org/f2.png")]}
        c["images"]["max_per_paper"] = 1
        attach_figures(p, c); attach_figures(p, c)
        self.assertEqual(len(p.figures), 1)
        c["images"]["mode"] = "off"; attach_figures(p, c)
        self.assertEqual(p.figures, [])

    def test_real_jats_relative_asset_links_without_invention(self):
        p, c = paper(pmcid="PMC42", open_access=True, authors=["Test Author"]), config()
        c["images"]["mode"] = "embed"
        xml = '''<article xmlns:xlink="http://www.w3.org/1999/xlink"><front><license xlink:href="https://creativecommons.org/licenses/by/4.0/"/></front>
        <body><p>''' + ("Synthetic evidence. " * 10) + '''</p><fig id="F1"><label>Figure 1</label><caption><p>A real caption in synthetic JATS.</p></caption><graphic xlink:href="relative-file.jpg"/></fig></body></article>'''
        enrich_full_text(p, FakeHttp(xml.encode()), c)
        self.assertTrue(p.full_text)
        self.assertEqual(p.figures[0]["source_url"], "https://europepmc.org/articles/PMC42#F1")
        self.assertEqual(p.figures[0]["url"], "")
        self.assertFalse(p.figures[0]["embed_allowed"])
        self.assertEqual(p.figures[0]["license_scope"], "unknown")

    def test_namespaced_jats_explicit_figure_permission(self):
        p, c = paper(pmcid="PMC42", open_access=True, authors=["Test Author"]), config(); c["images"]["mode"] = "embed"
        xml = '''<article xmlns="urn:jats:test" xmlns:xlink="http://www.w3.org/1999/xlink"><body><p>''' + ("Synthetic evidence. " * 10) + '''</p>
        <fig id="F1"><caption>Figure evidence.</caption><graphic xlink:href="https://cdn.example.org/f1.png"/>
        <permissions><license xlink:href="https://creativecommons.org/licenses/by/4.0/"/><copyright-holder>Figure Author</copyright-holder></permissions></fig></body></article>'''
        enrich_full_text(p, FakeHttp(xml.encode()), c)
        self.assertTrue(p.figures[0]["embed_allowed"])
        self.assertEqual(p.figures[0]["attribution"], "Figure Author")
        self.assertEqual(p.figures[0]["provenance"]["source"], "europepmc_jats")


if __name__ == "__main__":
    unittest.main()

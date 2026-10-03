"""Offline tests for agent-selected research tools and trusted URL resolution."""
import copy
import unittest
from unittest.mock import patch

from literature_digest.agent_sources import fetch, search
from literature_digest.config import DEFAULTS
from literature_digest.http import HttpClient, NoRedirect, RetrievalError
from literature_digest.sources import ARXIV, CROSSREF, EPMC


def config(**updates):
    result = copy.deepcopy(DEFAULTS)
    result.update(sources=["arxiv", "crossref", "europepmc"], page_size=10,
                  max_pages_per_query=1, retrieval_policy="bounded",
                  topics=[{"id": "climate", "name": "Climate", "queries": ["old query", "other old query"],
                           "source_queries": {"arxiv": ["old source override"]}},
                          {"id": "unrelated", "name": "Other", "queries": ["do not run"]}])
    result.update(updates)
    return result


class FakeHttp:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def request(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected source request: " + url)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    json = request


def crossref(doi="10.1234/synthetic", **changes):
    return {"message": {"DOI": doi, "title": ["Synthetic climate agent evidence"],
                        "abstract": "A source abstract, not agent-authored metadata.",
                        "type": "journal-article", "published-online": {"date-parts": [[2026, 10, 1]]},
                        "author": [{"given": "Synthetic", "family": "Author"}], **changes}}


def epmc_item(**changes):
    return {"source": "MED", "id": "12345", "pmcid": "PMC4567", "doi": "10.1234/synthetic",
            "title": "Synthetic climate agent evidence", "abstractText": "A Europe PMC abstract.",
            "electronicPublicationDate": "2026-10-01", "isOpenAccess": "Y", **changes}


def epmc(*items, total=None):
    return {"hitCount": len(items) if total is None else total, "resultList": {"result": list(items)}}


def arxiv(identifier="2610.01234v2", *, published="2026-10-01T12:34:56Z", total=1, offset=0):
    return (f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/">'
            f'<o:totalResults>{total}</o:totalResults><o:startIndex>{offset}</o:startIndex>'
            f'<entry><id>http://arxiv.org/abs/{identifier}</id><title>Synthetic climate agent</title>'
            f'<published>{published}</published><updated>2026-10-02T12:34:56Z</updated>'
            '<summary>An actual source abstract in an offline fixture.</summary></entry></feed>').encode()


class AgentSearchTests(unittest.TestCase):
    def test_only_selected_source_topic_query_no_model_or_config_mutation(self):
        cfg = config(llm={"enabled": True, "plan_queries": True, "screen_candidates": True})
        original = copy.deepcopy(cfg)
        http = FakeHttp(arxiv())
        with patch("literature_digest.analysis._model_request", side_effect=AssertionError("No model calls")):
            papers, report = search(cfg, "arxiv", "climate", "new climate agent", "2026-10-01", "2026-10-03", http)
        self.assertEqual(cfg, original)
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(http.calls[0][0], ARXIV)
        expression = http.calls[0][1]["params"]["search_query"]
        self.assertIn('all:"new" AND all:"climate" AND all:"agent"', expression)
        self.assertNotIn("old", expression)
        self.assertEqual(papers[0].tracks, [])  # Source tools do not decide relevance.
        self.assertEqual(papers[0].provenance[0]["topic_id"], "climate")
        self.assertEqual(report["agent_query"], "new climate agent")
        self.assertEqual(report["model_calls"], 0)
        self.assertEqual(report["requests"][0]["status"], "ok")

    def test_query_cannot_override_publication_window(self):
        http = FakeHttp(epmc())
        search(config(), "europepmc", "climate", 'agent") OR FIRST_PDATE:[1900 TO 2100]',
               "2026-10-01", "2026-10-03", http)
        expression = http.calls[0][1]["params"]["query"]
        self.assertEqual(expression.count("FIRST_PDATE:["), 1)
        self.assertIn("FIRST_PDATE:[2026-10-01 TO 2026-10-03]", expression)

    def test_caps_retain_honest_partial_coverage(self):
        http = FakeHttp(arxiv(total=200))
        papers, report = search(config(page_size=1), "arxiv", "climate", "agent", "2026-10-01", "2026-10-03", http)
        self.assertEqual(len(papers), 1)
        self.assertEqual(len(http.calls), 1)
        self.assertTrue(report["truncated"])
        self.assertFalse(report["complete"])
        with self.assertRaises(RetrievalError):
            search(config(page_size=1, retrieval_policy="complete"), "arxiv", "climate", "agent",
                   "2026-10-01", "2026-10-03", FakeHttp(arxiv(total=200)))

    def test_invalid_inputs_fail_before_http(self):
        cases = [
            ({"sources": ["crossref"]}, "arxiv", "climate", "agent", "2026-10-01", "2026-10-03"),
            ({}, "unknown", "climate", "agent", "2026-10-01", "2026-10-03"),
            ({}, "arxiv", "invented", "agent", "2026-10-01", "2026-10-03"),
            ({}, "arxiv", "climate", "\nquery", "2026-10-01", "2026-10-03"),
            ({}, "arxiv", "climate", "", "2026-10-01", "2026-10-03"),
            ({}, "arxiv", "climate", "x" * 501, "2026-10-01", "2026-10-03"),
            ({}, "arxiv", "climate", "agent", "20261001", "2026-10-03"),
            ({}, "arxiv", "climate", "agent", "2026-10-04", "2026-10-03"),
            ({"page_size": True}, "arxiv", "climate", "agent", "2026-10-01", "2026-10-03"),
            ({"max_pages_per_query": 0}, "arxiv", "climate", "agent", "2026-10-01", "2026-10-03"),
        ]
        for updates, *args in cases:
            with self.subTest(args=args, updates=updates):
                http = FakeHttp()
                with self.assertRaises(ValueError):
                    search(config(**updates), *args, http=http)
                self.assertEqual(http.calls, [])

    def test_legacy_topics_supported_without_running_legacy_queries(self):
        http = FakeHttp({"message": {"items": []}})
        _, report = search(config(topics=None), "crossref", "bvoc", "one new query", "2026-10-01", "2026-10-03", http)
        self.assertEqual(len(report["queries"]), 1)
        self.assertEqual(http.calls[0][1]["params"]["query"], "one new query")

    def test_malformed_response_is_retrieval_failure(self):
        for result in ([], {"message": None}, {"message": {"items": [None]}}):
            with self.subTest(result=result), self.assertRaises(RetrievalError):
                search(config(), "crossref", "climate", "agent", "2026-10-01", "2026-10-03", FakeHttp(result))



    def test_provider_cannot_exceed_configured_page_size(self):
        responses = [("crossref", {"message": {"items": [crossref()["message"], crossref()["message"]]}}),
                     ("europepmc", epmc(epmc_item(), epmc_item(id="12346"))),
                     ("arxiv", arxiv().replace(b"</feed>", arxiv().split(b"<entry>")[1].replace(b"</feed>", b"").join([b"<entry>", b""]) + b"</feed>"))]
        for source, response in responses:
            with self.subTest(source=source), self.assertRaises(RetrievalError):
                search(config(page_size=1), source, "climate", "agent", "2026-10-01", "2026-10-03", FakeHttp(response))

    def test_search_missing_stable_ids_cannot_become_evidence(self):
        cases = [("crossref", {"message": {"items": [{"title": ["Synthetic"], "URL": "https://evil.example/item"}]}}),
                 ("europepmc", epmc(epmc_item(id="12345 OR anything")))]
        for source, response in cases:
            with self.subTest(source=source), self.assertRaises(RetrievalError):
                search(config(), source, "climate", "agent", "2026-10-01", "2026-10-03", FakeHttp(response))


class AgentFetchTests(unittest.TestCase):
    def test_arxiv_abs_pdf_html_resolve_via_api_preserving_version(self):
        for url in ("https://arxiv.org/abs/2610.01234v2", "https://arxiv.org/pdf/2610.01234v2.pdf",
                    "https://www.arxiv.org/html/2610.01234v2", "https://export.arxiv.org/abs/2610.01234"):
            with self.subTest(url=url):
                http = FakeHttp(arxiv())
                papers, report = fetch(config(), url, http)
                self.assertEqual(len(papers), 1)
                self.assertEqual(papers[0].key, "arxiv:2610.01234")
                self.assertEqual(papers[0].source_id, "2610.01234v2")
                self.assertEqual(papers[0].publication_date, "2026-10-01")
                self.assertEqual(papers[0].evidence_level, "仅摘要")
                self.assertEqual(papers[0].provenance[0]["requested_url"], url)
                self.assertEqual(report["requested_url"], url)
                self.assertTrue(report["identity_verified"])
                self.assertEqual(http.calls[0][0], ARXIV)
                self.assertEqual(report["requests"][0]["query"], http.calls[0][1]["params"])

    def test_legacy_arxiv_id(self):
        papers, _ = fetch(config(), "https://arxiv.org/abs/hep-th/9901001v12", FakeHttp(arxiv("hep-th/9901001v12")))
        self.assertEqual(papers[0].arxiv_id, "hep-th/9901001")

    def test_arxiv_wrong_id_or_version_never_imported(self):
        for returned in ("2610.99999v2", "2610.01234v3", "http://evil.example/abs/2610.01234v2"):
            with self.subTest(returned=returned), self.assertRaises(RetrievalError):
                fetch(config(), "https://arxiv.org/abs/2610.01234v2", FakeHttp(arxiv(returned)))

    def test_doi_and_crossref_url_get_verified_online_metadata(self):
        for url in ("https://doi.org/10.1234/SYNTHETIC", "https://api.crossref.org/works/10.1234%2Fsynthetic"):
            http = FakeHttp(crossref(URL="http://untrusted.example/article"))
            papers, report = fetch(config(), url, http)
            self.assertEqual(papers[0].doi, "10.1234/synthetic")
            self.assertEqual(papers[0].url, "https://doi.org/10.1234/synthetic")
            self.assertEqual(papers[0].publication_date, "2026-10-01")
            self.assertEqual(papers[0].provenance[0]["date_fields"]["published-online"]["date-parts"], [[2026, 10, 1]])
            self.assertEqual(http.calls[0][0], CROSSREF + "/10.1234%2Fsynthetic")
            self.assertEqual(report["optional_europepmc_lookup"], "not_needed")
            self.assertEqual(len(http.calls), 1)

    def test_doi_mismatch_or_missing_title_fail(self):
        for result in (crossref(doi="10.1234/wrong"), crossref(title=[]), crossref(title="Wrong shape"),
                       {"message": None}, []):
            with self.subTest(result=result), self.assertRaises(RetrievalError):
                fetch(config(), "https://doi.org/10.1234/synthetic", FakeHttp(result))

    def test_doi_fills_abstract_through_exact_epmc_evidence(self):
        http = FakeHttp(crossref(abstract=""), epmc(epmc_item()))
        papers, report = fetch(config(), "https://doi.org/10.1234/synthetic", http)
        self.assertEqual(len(papers), 2)
        self.assertEqual(papers[0].key, papers[1].key)
        self.assertEqual(papers[1].abstract, "A Europe PMC abstract.")
        self.assertEqual(papers[1].pmcid, "PMC4567")
        self.assertEqual(report["optional_europepmc_lookup"], "found")
        self.assertEqual(http.calls[1][0], EPMC + "/search")
        self.assertEqual(http.calls[1][1]["params"]["query"], 'DOI:"10.1234/synthetic"')

    def test_disabled_epmc_is_never_contacted(self):
        http = FakeHttp(crossref(abstract=""))
        papers, report = fetch(config(sources=["crossref"]), "https://doi.org/10.1234/synthetic", http)
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(report["optional_europepmc_lookup"], "source_disabled")
        self.assertEqual(papers[0].evidence_level, "仅元数据")

    def test_optional_transport_failure_disclosed_no_match_distinct(self):
        for response, status in ((RetrievalError("HTTP 503"), "failed"), (epmc(), "no_match")):
            with self.subTest(status=status):
                papers, report = fetch(config(), "https://doi.org/10.1234/synthetic", FakeHttp(crossref(abstract=""), response))
                self.assertEqual(len(papers), 1)
                self.assertEqual(report["optional_europepmc_lookup"], status)
                self.assertEqual(report["complete"], status != "failed")
                self.assertEqual(bool(report["warnings"]), status == "failed")
                self.assertEqual(bool(papers[0].warnings), status == "failed")

    def test_optional_mismatch_or_truncation_is_not_ignored(self):
        for response in (epmc(epmc_item(doi="10.1234/wrong")), epmc(epmc_item(), total=2)):
            with self.subTest(response=response), self.assertRaises(RetrievalError):
                fetch(config(), "https://doi.org/10.1234/synthetic", FakeHttp(crossref(abstract=""), response))

    def test_pmc_and_epmc_families_resolve_matching_identity(self):
        urls = ["https://europepmc.org/article/MED/12345", "https://europepmc.org/article/PMC/PMC4567",
                "https://www.europepmc.org/articles/PMC4567/", "https://pmc.ncbi.nlm.nih.gov/articles/PMC4567/",
                "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4567/"]
        for url in urls:
            with self.subTest(url=url):
                http = FakeHttp(epmc(epmc_item()))
                papers, report = fetch(config(), url, http)
                self.assertEqual(papers[0].source_id, "MED:12345")
                self.assertEqual(papers[0].pmcid, "PMC4567")
                self.assertEqual(http.calls[0][0], EPMC + "/search")
                self.assertTrue(report["identity_verified"])
        paper, _ = fetch(config(), "https://europepmc.org/article/PPR/PPR42", FakeHttp(epmc(epmc_item(source="PPR", id="PPR42"))))
        self.assertIn("预印本", paper[0].kind)

    def test_epmc_mismatch_source_id_pmcid_and_missing_record_fail(self):
        cases = [("MED/12345", epmc(epmc_item(id="999"))),
                 ("MED/12345", epmc(epmc_item(source="PPR", id="PPR12345"))),
                 ("MED/12345", epmc(epmc_item(source="EVIL"))),
                 ("PMC/PMC4567", epmc(epmc_item(pmcid="PMC999"))),
                 ("MED/12345", epmc()), ("MED/12345", epmc(epmc_item(), total=2)),
                 ("MED/12345", {"hitCount": 1, "resultList": None})]
        for path, response in cases:
            with self.subTest(path=path, response=response), self.assertRaises(RetrievalError):
                fetch(config(), "https://europepmc.org/article/" + path, FakeHttp(response))

    def test_full_text_uses_existing_parser_and_records_actual_request(self):
        text = "Synthetic methods and results evidence. " * 30
        html = f'<article class="ltx_document"><section><p>{text}</p></section></article>'.encode()
        http = FakeHttp(arxiv(), html)
        papers, report = fetch(config(fetch_full_text=True), "https://arxiv.org/pdf/2610.01234v2.pdf", http)
        self.assertTrue(papers[0].full_text)
        self.assertEqual(papers[0].full_text_url, "https://arxiv.org/html/2610.01234v2")
        self.assertEqual(report["requests"][-1]["api_url"], papers[0].full_text_url)
        self.assertEqual(len(http.calls), 2)

    def test_pmc_full_text_opt_in_and_failure_warning(self):
        xml = ("<article><body><p>" + "Synthetic body evidence. " * 10 + "</p></body></article>").encode()
        http = FakeHttp(epmc(epmc_item()), xml)
        papers, _ = fetch(config(fetch_full_text=True), "https://pmc.ncbi.nlm.nih.gov/articles/PMC4567/", http)
        self.assertTrue(papers[0].full_text)
        self.assertEqual(http.calls[-1][0], EPMC + "/PMC4567/fullTextXML")
        http = FakeHttp(arxiv(), RetrievalError("HTML unavailable"))
        papers, report = fetch(config(fetch_full_text=True), "https://arxiv.org/abs/2610.01234v2", http)
        self.assertFalse(papers[0].full_text)
        self.assertTrue(papers[0].warnings)
        self.assertEqual(report["requests"][-1]["status"], "error")

    def test_fulltext_does_not_enable_unconfigured_arxiv(self):
        http = FakeHttp(crossref(doi="10.48550/arxiv.2610.01234"))
        papers, _ = fetch(config(sources=["crossref"], fetch_full_text=True),
                          "https://doi.org/10.48550/arxiv.2610.01234", http)
        self.assertFalse(papers[0].full_text)
        self.assertEqual(len(http.calls), 1)



    def test_mismatched_fulltext_identity_never_becomes_evidence(self):
        xml = ("<article><front><article-id pub-id-type=\"pmc\">999</article-id></front><body><p>"
               + "Synthetic evidence body. " * 10 + "</p></body></article>").encode()
        papers, report = fetch(config(fetch_full_text=True), "https://europepmc.org/articles/PMC4567",
                               FakeHttp(epmc(epmc_item()), xml))
        self.assertFalse(papers[0].full_text)
        self.assertTrue(any("different article" in warning for warning in papers[0].warnings))
        self.assertEqual(report["full_text_retrieved"], 0)


class AgentURLSecurityTests(unittest.TestCase):
    def test_ssrf_credentials_ports_query_fragments_and_injections_rejected(self):
        urls = [
            "http://arxiv.org/abs/2610.01234", "file:///etc/passwd", "https://127.0.0.1/abs/2610.01234",
            "https://[::1]/abs/2610.01234", "https://localhost/abs/2610.01234",
            "https://arxiv.org.evil.example/abs/2610.01234", "https://arxiv.org./abs/2610.01234",
            "https://user:pass@arxiv.org/abs/2610.01234", "https://@arxiv.org/abs/2610.01234",
            "https://arxiv.org:443/abs/2610.01234", "https://arxiv.org:8443/abs/2610.01234",
            "https://arxiv.org/abs/2610.01234?download=1", "https://arxiv.org/abs/2610.01234?",
            "https://arxiv.org/abs/2610.01234#", "https://arxiv.org/abs/2610.01234#fragment",
            "https://arxiv.org\\@localhost/abs/2610.01234", " https://arxiv.org/abs/2610.01234",
            "https://arxiv.org/abs/2610.01234\n", "https://arxiv.org/abs/%32%36%31%30.01234",
            "https://arxiv.org/abs/2610.01234,2610.99999", "https://arxiv.org/html/2610.01234.pdf",
            "https://doi.org/10.1234/foo/../bar", "https://doi.org/10.1234/%252fsecret",
            "https://doi.org/10.1234/synthetic%3Fredirect=https://evil.example",
            "https://doi.org/10.1234/synthetic%23fragment", "https://doi.org/10.1234/%0Ainjected",
            "https://doi.org/doi:10.1234/synthetic", "https://doi.org/10.1234/%22%20OR%20EXT_ID:42",
            "https://api.crossref.org/works?filter=from-pub-date:2026-01-01",
            "https://api.crossref.org/works", "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=anything",
            "https://europepmc.org/article/MED/12345%20OR%20SRC:PPR", "https://europepmc.org/article/MED/PPR42",
            "https://europepmc.org/article/PMC/42", "https://pmc.ncbi.nlm.nih.gov/articles/PMC4567/../../secret",
            "https://publisher.example/article", {"title": "Caller-authored evidence"}, None,
        ]
        for url in urls:
            with self.subTest(url=url):
                http = FakeHttp()
                with self.assertRaises(ValueError):
                    fetch(config(), url, http)
                self.assertEqual(http.calls, [])

    def test_disabled_primary_source_rejected_before_network(self):
        http = FakeHttp()
        with self.assertRaisesRegex(ValueError, "not enabled"):
            fetch(config(sources=["crossref"]), "https://arxiv.org/abs/2610.01234", http)
        self.assertEqual(http.calls, [])

    def test_network_failure_and_redirect_are_not_empty_success(self):
        for failure in ("HTTP 404", "HTTP 503", "API redirect denied"):
            with self.subTest(failure=failure), self.assertRaises(RetrievalError):
                fetch(config(), "https://arxiv.org/abs/2610.01234", FakeHttp(RetrievalError(failure)))
        with self.assertRaises(RetrievalError):
            NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://127.0.0.1/private")

    def test_default_http_client_retains_redirect_denial(self):
        client = HttpClient(sleeper=lambda _: None)
        handlers = client.opener.__self__.handlers
        self.assertTrue(any(isinstance(handler, NoRedirect) for handler in handlers))

    def test_fetch_has_zero_model_calls_even_when_llm_enabled(self):
        cfg = config(llm={"enabled": True, "backend": "api", "plan_queries": True})
        with patch("literature_digest.analysis._model_request", side_effect=AssertionError("No model calls")):
            papers, report = fetch(cfg, "https://doi.org/10.1234/synthetic", FakeHttp(crossref()))
        self.assertEqual(len(papers), 1)
        self.assertEqual(report["model_calls"], 0)



def abs_html(identifier="2610.01234", version="2610.01234v2", first="Thu, 1 Oct 2026 12:34:56 UTC"):
    # Minimal synthetic fixture of the official citation/arxivid/history regions.
    return (f'<html><head><link rel="canonical" href="https://arxiv.org/abs/{identifier}"/>'
            f'<meta name="citation_arxiv_id" content="{identifier}"/>'
            '<meta name="citation_title" content="Synthetic source title"/>'
            '<meta name="citation_author" content="Synthetic Author"/>'
            '<meta name="citation_date" content="2026/10/03"/>'
            '<meta name="citation_online_date" content="2026/10/03"/>'
            '<meta name="citation_abstract" content="Synthetic source abstract."/></head><body>'
            '<td class="tablecell arxivid"><a>arXiv:' + identifier + '</a></td><td class="tablecell arxividv">'
            '(or <span class="arxivid"><a href="https://arxiv.org/abs/' + version + '">arXiv:' + version + '</a>'
            ' [cs.AI]</span> for this version)</td><div class="submission-history"><h2>Submission history</h2>'
            f'<strong>[v1]</strong> {first} (100 KB)<br/>'
            '<strong>[v2]</strong> Sat, 3 Oct 2026 12:34:56 UTC (101 KB)</div></body></html>').encode()


class ArxivAbsFallbackTests(unittest.TestCase):
    def test_fallback_verifies_first_submission_not_latest_citation_date(self):
        http = FakeHttp(RetrievalError("export.arxiv.org HTTP 429"), abs_html())
        papers, report = fetch(config(), "https://arxiv.org/abs/2610.01234v2", http)
        paper = papers[0]
        self.assertEqual(paper.publication_date, "2026-10-01")
        self.assertEqual(paper.source_id, "2610.01234v2")
        self.assertEqual(paper.abstract, "Synthetic source abstract.")
        self.assertEqual(paper.provenance[0]["format"], "arxiv_abstract_html")
        self.assertEqual(paper.provenance[0]["date_fields"]["arxiv-published"], "2026-10-01")
        self.assertEqual(http.calls[1][0], "https://arxiv.org/abs/2610.01234v2")
        self.assertEqual([r["status"] for r in report["requests"]], ["error", "ok"])
        self.assertTrue(paper.warnings)

    def test_network_failure_can_use_official_page(self):
        http = FakeHttp(RetrievalError("export.arxiv.org 网络连接失败（TimeoutError）"), abs_html())
        papers, _ = fetch(config(), "https://arxiv.org/html/2610.01234", http)
        self.assertEqual(papers[0].source_id, "2610.01234v2")
        self.assertEqual(http.calls[1][0], "https://arxiv.org/abs/2610.01234")

    def test_fallback_rejects_mismatch_missing_history_ambiguous_or_invalid_date(self):
        pages = [abs_html(identifier="2610.99999"), abs_html(version="2610.01234v3"),
                 abs_html().replace(b'[v1]', b'[v9]'),
                 abs_html(first="Fri, 31 Feb 2026 12:34:56 UTC"),
                 abs_html().replace(b'UTC (100 KB)', b'(100 KB)'),
                 abs_html().replace(b'class="submission-history"', b'class="unrelated"'),
                 abs_html().replace(b'for this version', b'previous version'),
                 abs_html().replace(b'content="2610.01234"', b'content="2610.99999"'),
                 abs_html().replace(b'<strong>[v2]</strong>', b'<strong>[v1]</strong>'),
                 b'<html><meta name="citation_date" content="2026/10/03"/></html>']
        for page in pages:
            with self.subTest(page=page[:100]), self.assertRaises(RetrievalError):
                fetch(config(), "https://arxiv.org/abs/2610.01234v2", FakeHttp(RetrievalError("HTTP 429"), page))

    def test_redirects_access_denials_and_malformed_api_do_not_trigger_fallback(self):
        for failure in (RetrievalError("HTTP 403"), RetrievalError("HTTP 401"), RetrievalError("HTTP 404"),
                        RetrievalError("API 重定向已拒绝"), b'<html>Not Atom</html>', arxiv("2610.99999v2")):
            http = FakeHttp(failure)
            with self.subTest(failure=failure), self.assertRaises(RetrievalError):
                fetch(config(), "https://arxiv.org/abs/2610.01234v2", http)
            self.assertEqual(len(http.calls), 1)

    def test_abs_failure_is_a_failure_no_more_hosts_or_requests(self):
        http = FakeHttp(RetrievalError("HTTP 429"), RetrievalError("HTTP 429"))
        with self.assertRaises(RetrievalError):
            fetch(config(), "https://arxiv.org/abs/2610.01234v2", http)
        self.assertEqual(len(http.calls), 2)

    def test_verified_abs_can_then_enrich_original_html_body(self):
        prose = "Synthetic article body evidence. " * 25
        body = f'<article class="ltx_document"><p>{prose}</p></article>'.encode()
        http = FakeHttp(RetrievalError("HTTP 429"), abs_html(), body)
        papers, report = fetch(config(fetch_full_text=True), "https://arxiv.org/html/2610.01234v2", http)
        self.assertTrue(papers[0].full_text)
        self.assertEqual(papers[0].publication_date, "2026-10-01")
        self.assertEqual(len(report["requests"]), 3)


if __name__ == "__main__":
    unittest.main()

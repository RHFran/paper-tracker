"""Explicit query caps disclose partial coverage; provider failures stay failures."""
import unittest

from literature_digest.http import RetrievalError
from literature_digest.sources import fetch_arxiv, fetch_crossref, fetch_europepmc


class FakeHttp:
    def __init__(self, *responses):
        self.responses, self.calls = iter(responses), []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value

    json = request


def config(policy="complete"):
    return {"topics": [{"id": "agents", "queries": ["weather agent"]}],
            "page_size": 1, "max_pages_per_query": 1, "contact_email": "",
            "retrieval_policy": policy}


def crossref(total=1000, cursor="next"):
    return {"message": {"items": [{"title": ["Synthetic weather agent"], "DOI": "10.1234/synthetic"}],
                        "total-results": total, "next-cursor": cursor}}


def epmc(total=1000, cursor="next"):
    return {"hitCount": total, "nextCursorMark": cursor,
            "resultList": {"result": [{"title": "Synthetic weather agent", "source": "MED", "id": "42"}]}}


def arxiv(total=1000, identifier="2601.00001v1", offset=0):
    return f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/">
    <o:totalResults>{total}</o:totalResults><o:startIndex>{offset}</o:startIndex>
    <entry><id>http://arxiv.org/abs/{identifier}</id><title>Synthetic weather agent</title>
    <published>2026-01-01T00:00:00Z</published></entry></feed>'''.encode()


class BoundedSourceTests(unittest.TestCase):
    adapters = ((fetch_crossref, crossref), (fetch_europepmc, epmc), (fetch_arxiv, arxiv))

    def test_explicit_bounded_cap_is_partial_not_outage(self):
        for fetch, result in self.adapters:
            with self.subTest(source=fetch.__name__):
                http = FakeHttp(result())
                papers, report = fetch(http, config("bounded"), "2026-01-01", "2026-10-03", True)
                self.assertEqual(len(http.calls), 1)
                self.assertEqual(len(papers), 1)
                self.assertFalse(report["complete"])
                self.assertTrue(report["truncated"])
                self.assertEqual(report["retrieval_policy"], "bounded")
                self.assertIn("not an exhaustive", report["coverage_note"])
                query = report["queries"][0]
                self.assertEqual(query["reason"], "configured_max_pages_per_query")
                self.assertEqual(query["records_retrieved"], 1)
                self.assertEqual(query["total_results"], 1000)
                self.assertFalse(query["complete"])
                self.assertTrue(query["order"])

    def test_implicit_and_explicit_complete_still_fail_at_limit(self):
        for fetch, result in self.adapters:
            for implicit in (False, True):
                with self.subTest(source=fetch.__name__, implicit=implicit):
                    cfg = config()
                    if implicit:
                        cfg.pop("retrieval_policy")
                    with self.assertRaises(RetrievalError):
                        fetch(FakeHttp(result()), cfg, "2026-01-01", "2026-10-03", True)

    def test_bounded_results_can_finish_complete(self):
        for fetch, result in self.adapters:
            with self.subTest(source=fetch.__name__):
                papers, report = fetch(FakeHttp(result(total=1)), config("bounded"), "2026-01-01", "2026-10-03", True)
                self.assertEqual(len(papers), 1)
                self.assertTrue(report["complete"])
                self.assertFalse(report["truncated"])
                self.assertNotIn("coverage_note", report)

    def test_crossref_bounded_requests_explicit_relevance_order(self):
        http = FakeHttp(crossref())
        fetch_crossref(http, config("bounded"), "2026-01-01", "2026-10-03", True)
        self.assertEqual(http.calls[0][1]["params"]["sort"], "score")
        self.assertEqual(http.calls[0][1]["params"]["order"], "desc")

    def test_bounded_does_not_swallow_transport_or_malformed_pages(self):
        for fetch, response in ((fetch_crossref, crossref(cursor="*")),
                                (fetch_europepmc, epmc(cursor="*")),
                                (fetch_arxiv, arxiv(offset=3))):
            with self.subTest(source=fetch.__name__), self.assertRaises(RetrievalError):
                fetch(FakeHttp(response), config("bounded"), "2026-01-01", "2026-10-03", True)
        for fetch, _ in self.adapters:
            with self.subTest(source=fetch.__name__), self.assertRaises(RetrievalError):
                fetch(FakeHttp(RetrievalError("HTTP 429")), config("bounded"), "2026-01-01", "2026-10-03", True)

    def test_multiple_queries_keep_independent_coverage(self):
        cfg = config("bounded")
        cfg["topics"][0]["queries"].append("climate agent")
        http = FakeHttp(crossref(), {"message": {"items": [], "total-results": 0}})
        _, report = fetch_crossref(http, cfg, "2026-01-01", "2026-10-03", True)
        self.assertFalse(report["complete"])
        self.assertTrue(report["queries"][0]["truncated"])
        self.assertTrue(report["queries"][1]["complete"])


if __name__ == "__main__":
    unittest.main()

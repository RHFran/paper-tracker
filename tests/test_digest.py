"""Offline fixtures are synthetic test records, not claims about real research."""
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, date
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from literature_digest.analysis import analyze, validate_analysis, FIELDS
from literature_digest.config import DEFAULTS, load_config
from literature_digest.http import HttpClient, RetrievalError, NoRedirect
from urllib.request import Request
from literature_digest.mail import send_smtp, DeliveryUncertain, MailSetupError
from literature_digest.models import Paper, normalize_doi, parse_date_parts
from literature_digest.pipeline import run, verified_online_date
from literature_digest.relevance import classify, merge_papers
from literature_digest.sources import fetch_crossref, fetch_europepmc, crossref_paper, epmc_paper, enrich_full_text
from literature_digest.state import State, state_scope


def paper(day="2026-10-01", doi="10.9999/test-only", title="Biogenic volatile organic compound emissions from trees", abstract="Synthetic test abstract, not a real publication."):
    return Paper(title=title, source_id=doi, source="crossref", doi=doi, url="https://doi.org/" + doi, abstract=abstract,
                 provenance=[{"date_fields": {"published-online": {"date-parts": [[int(p) for p in day.split('-')]]}}}])


class FakeHttp:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def json(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return next(self.responses)


class ConfigTest(unittest.TestCase):
    def test_seven_day_default_and_dry_run(self):
        self.assertEqual(DEFAULTS["publication_window_days"], 7)
        self.assertFalse(DEFAULTS["mail"]["enabled"])
        self.assertFalse(DEFAULTS["llm"]["enabled"])
    def test_bad_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text('{"sources":["bogus"]}')
            with self.assertRaises(ValueError):
                load_config(str(path))
    def test_recipient_header_injection_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps({"recipient": "a@b\nBcc:x@y"}))
            with self.assertRaises(ValueError):
                load_config(str(path))


class MetadataTest(unittest.TestCase):
    def test_doi_normalization(self):
        self.assertEqual(normalize_doi(" HTTPS://DOI.ORG/10.1234/AbC "), "10.1234/abc")
    def test_partial_dates_not_invented(self):
        self.assertEqual(parse_date_parts({"date-parts": [[2026]]}), "2026")
        self.assertEqual(parse_date_parts({"date-parts": [[2026, 9]]}), "2026-09")
        self.assertEqual(parse_date_parts({"date-parts": [[2026, 2, 31]]}), "")
    def test_online_date_required(self):
        p = paper()
        p.provenance = [{"date_fields": {"published-print": {"date-parts": [[2026, 10, 1]]}}}]
        self.assertIsNone(verified_online_date(p))
    def test_online_conflict_withheld(self):
        p = paper()
        p.provenance.append({"date_fields": {"electronicPublicationDate": "2026-09-30"}})
        self.assertIsNone(verified_online_date(p))
    def test_crossref_metadata_no_peer_review_claim(self):
        p = crossref_paper({"title": ["Test"], "DOI": "10.1/X", "type": "journal-article", "published-online": {"date-parts": [[2026, 10, 1]]}}, {})
        self.assertIn("未", p.kind)
        self.assertEqual(p.publication_date, "2026-10-01")
    def test_preprint_explicit(self):
        p = epmc_paper({"source": "PPR", "id": "1", "title": "Synthetic"}, {})
        self.assertIn("预印本", p.kind)


class RelevanceTest(unittest.TestCase):
    def test_two_tracks_independent(self):
        self.assertEqual(classify(paper()), ["bvoc"])
        self.assertEqual(classify(paper(title="Tree species classification using hyperspectral satellite imagery")), ["tree_species"])
    def test_hyphenated_tree_species_and_acronym_context(self):
        self.assertEqual(classify(paper(title="Tree-species classification using hyperspectral imagery")), ["tree_species"])
        self.assertEqual(classify(paper(title="BVOC emissions and atmospheric chemistry")), ["bvoc"])
    def test_unrelated_bvoc_excluded(self):
        self.assertEqual(classify(paper(title="BVOC vocational education college survey", abstract="A survey of students and business courses.")), [])
    def test_biological_context_required_for_isoprene(self):
        self.assertEqual(classify(paper(title="Industrial isoprene polymer synthesis", abstract="Chemical manufacturing methods.")), [])
        self.assertEqual(classify(paper(title="Isoprene emissions from soil microbes", abstract="Microbial volatile chemistry.")), ["bvoc"])
    def test_industrial_plant_is_not_biogenic(self):
        self.assertEqual(classify(paper(title="Power plant volatile organic compounds emissions", abstract="Industrial stack measurements.")), [])
    def test_tree_species_without_sensing_excluded(self):
        self.assertEqual(classify(paper(title="Tree species classification by DNA barcoding")), [])
    def test_merge_aliases_and_abstract(self):
        a, b = paper(), paper(doi="HTTPS://DOI.ORG/10.9999/TEST-ONLY", abstract="A longer synthetic abstract for testing, not research.")
        b.source, b.source_id, b.pmcid = "europepmc", "MED:42", "PMC42"
        merged = merge_papers([a, b])
        self.assertEqual(len(merged), 1)
        self.assertIn("europepmc:MED:42", merged[0].aliases)
        self.assertIn("longer", merged[0].abstract)


class SourcesTest(unittest.TestCase):
    def test_crossref_date_filter_and_cursor(self):
        one = {"title": ["Synthetic"], "DOI": "10.9999/1"}
        http = FakeHttp([{"message": {"items": [one], "next-cursor": "next"}}, {"message": {"items": []}}])
        c = copy.deepcopy(DEFAULTS); c["page_size"] = 1
        with patch("literature_digest.sources.BVOC_QUERIES", ["biogenic"]), patch("literature_digest.sources.TREE_QUERIES", []):
            papers, report = fetch_crossref(http, c, "2026-09-30", "2026-10-01", False)
        self.assertEqual(len(papers), 1)
        self.assertIn("until-index-date:2026-10-01", http.calls[0][1]["params"]["filter"])
        self.assertEqual(http.calls[1][1]["params"]["cursor"], "next")
    def test_crossref_truncation_is_failure(self):
        http = FakeHttp([{"message": {"items": [{"title": ["Synthetic"]}], "next-cursor": "next"}}])
        c = copy.deepcopy(DEFAULTS); c.update(page_size=1, max_pages_per_query=1)
        with patch("literature_digest.sources.BVOC_QUERIES", ["x"]), patch("literature_digest.sources.TREE_QUERIES", []):
            with self.assertRaises(RetrievalError):
                fetch_crossref(http, c, "2026-10-01", "2026-10-01", True)
    def test_epmc_cursor_and_core(self):
        http = FakeHttp([{"hitCount": 2, "resultList": {"result": [{"title": "A", "id": "1"}]}, "nextCursorMark": "next"}, {"hitCount": 2, "resultList": {"result": [{"title": "B", "id": "2"}]}}])
        c = copy.deepcopy(DEFAULTS); c["page_size"] = 1
        with patch("literature_digest.sources.EPMC_QUERIES", {"bvoc": "x"}):
            papers, _ = fetch_europepmc(http, c, "2026-10-01", "2026-10-01", False)
        self.assertEqual(len(papers), 2)
        self.assertEqual(http.calls[0][1]["params"]["resultType"], "core")
        self.assertIn("FIRST_IDATE", http.calls[0][1]["params"]["query"])
    def test_epmc_incomplete_is_failure(self):
        http = FakeHttp([{"hitCount": 2, "resultList": {"result": []}}])
        with patch("literature_digest.sources.EPMC_QUERIES", {"bvoc": "x"}):
            with self.assertRaises(RetrievalError):
                fetch_europepmc(http, DEFAULTS, "2026-10-01", "2026-10-01", False)
    def test_fulltext_error_downgrades(self):
        p = paper(); p.pmcid = "PMC1"; p.open_access = True
        class Failed:
            def request(self, *a, **k): raise RetrievalError("404")
        enrich_full_text(p, Failed())
        self.assertFalse(p.full_text)
        self.assertTrue(p.warnings)


class HttpTest(unittest.TestCase):
    def test_retry_after_then_success(self):
        calls, sleeps = [], []
        def opener(req, timeout):
            calls.append(req)
            if len(calls) == 1:
                raise HTTPError(req.full_url, 429, "Busy", {"Retry-After": "2"}, None)
            return io.BytesIO(b'{"ok":true}')
        http = HttpClient(opener=opener, sleeper=sleeps.append)
        self.assertTrue(http.json("https://example.test/api")["ok"])
        self.assertIn(2.0, sleeps)
    def test_network_failure_never_empty(self):
        def opener(*a, **k): raise URLError("blocked")
        with self.assertRaises(RetrievalError):
            HttpClient(opener=opener, sleeper=lambda _: None).json("https://example.test")
    def test_bearer_redirect_rejected(self):
        req = Request("https://provider.test/v1/chat/completions", headers={"Authorization": "Bearer synthetic"})
        with self.assertRaises(RetrievalError):
            NoRedirect().redirect_request(req, None, 302, "Found", {}, "http://other.test")
    def test_plaintext_api_rejected(self):
        with self.assertRaises(RetrievalError):
            HttpClient().json("http://example.test")


class AnalysisTest(unittest.TestCase):
    def test_missing_llm_safe_fallback(self):
        c = copy.deepcopy(DEFAULTS); c["llm"]["enabled"] = True
        self.assertEqual(analyze(paper(), c, None)["mode"], "discovery_only")
    def test_evidence_anchor_enforced(self):
        data = {k: [] for k in FIELDS}
        data["methods"] = [{"text": "采用测试方法", "evidence": "The exact source anchor."}]
        self.assertTrue(validate_analysis(data, "The exact source anchor.")["methods"])
        with self.assertRaises(ValueError):
            validate_analysis(data, "A different source.")
    def test_no_model_no_deep_analysis(self):
        self.assertEqual(analyze(paper(), DEFAULTS, None)["mode"], "discovery_only")


from model_fixture import install_model_double, enable_model


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.c = copy.deepcopy(DEFAULTS)
        self.c.update(state_path=str(Path(self.temp.name) / "state.db"), output_dir=str(Path(self.temp.name) / "output"), sources=["crossref"])
        self.now = datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc)  # Oct 2 in Shanghai.
        install_model_double(self, self.c)
    def tearDown(self): self.temp.cleanup()
    def fetcher(self, records):
        return {"crossref": lambda *args: (copy.deepcopy(records), {"source": "crossref", "complete": True})}
    def test_only_seven_day_online_dates(self):
        records = [paper("2026-09-25", "10.9999/in"), paper("2026-09-24", "10.9999/old"), paper("2026-10-03", "10.9999/future"), paper("2026-10", "10.9999/partial")]
        result = run(self.c, now=self.now, fetchers=self.fetcher(records))
        self.assertEqual(result["paper_count"], 1)
        audit = json.loads(Path(result["paths"]["json"]).read_text(encoding="utf-8"))
        self.assertEqual(audit["meta"]["publication_start"], "2026-09-25")
        self.assertIn("边界日", audit["papers"][0]["warnings"][0])
        self.assertEqual(audit["meta"]["outside_window"], 2)
        self.assertEqual(audit["meta"]["date_unknown"], 1)
    def test_every_run_rescans_full_seven_days(self):
        state = State(self.c["state_path"], scope=state_scope(self.c))
        state.prepare("prior", {"aliases": [], "harvest_until": "2026-10-01"})
        state.mark_sent("prior"); state.close()
        calls = []
        def fetcher(http, config, start, end, initial):
            calls.append((start, end, initial))
            return [paper("2026-09-25")], {"complete": True}
        result = run(self.c, now=self.now, fetchers={"crossref": fetcher})
        self.assertEqual(calls, [("2026-09-25", "2026-10-02", True)])
        self.assertEqual(result["paper_count"], 1)
    def test_preview_never_marks_sent_or_checkpoint(self):
        result = run(self.c, now=self.now, fetchers=self.fetcher([paper()]))
        self.assertEqual(result["status"], "dry_run")
        state = State(self.c["state_path"], scope=state_scope(self.c))
        self.assertIsNone(state.checkpoint()); self.assertFalse(state.was_sent(paper())); state.close()
    def test_failed_source_not_no_new(self):
        def failed(*a): raise RetrievalError("rate limited")
        result = run(self.c, send=True, now=self.now, fetchers={"crossref": failed}, mail_adapter=lambda *a: self.fail("Must not send"))
        self.assertEqual(result["status"], "retrieval_failed")
        self.assertIn("不能判断是否有新论文", Path(result["paths"]["txt"]).read_text(encoding="utf-8"))
        state = State(self.c["state_path"], scope=state_scope(self.c)); self.assertIsNone(state.checkpoint()); state.close()
    def test_sent_idempotent_and_durable_dedup(self):
        calls = []
        def sender(payload, config, state, id_):
            calls.append(id_); state.mark_sent(id_)
        a = run(self.c, send=True, now=self.now, fetchers=self.fetcher([paper()]), mail_adapter=sender)
        b = run(self.c, send=True, now=self.now, fetchers=self.fetcher([paper()]), mail_adapter=sender)
        self.assertEqual(b["status"], "already_sent"); self.assertEqual(len(calls), 1)
        c = run(self.c, now=datetime(2026, 10, 2, 23, tzinfo=timezone.utc), fetchers=self.fetcher([paper()]))
        self.assertEqual(c["paper_count"], 0)
    def test_html_untrusted_text_escaped(self):
        result = run(self.c, now=self.now, fetchers=self.fetcher([paper(title="<script>alert(1)</script> Biogenic volatile organic compounds")]))
        html = Path(result["paths"]["html"]).read_text(encoding="utf-8")
        self.assertNotIn("<script>", html); self.assertIn("&lt;script&gt;", html)
    def test_uncertain_state_blocks_future_send(self):
        state = State(self.c["state_path"], scope=state_scope(self.c))
        state.prepare("old", {"aliases": [], "harvest_until": "2026-10-01"}); state.status("old", "sending"); state.close()
        with self.assertRaises(RuntimeError):
            run(self.c, send=True, now=self.now, fetchers=self.fetcher([]))


class MailTest(unittest.TestCase):
    def send(self, *args, **kwargs):
        return send_smtp(*args, **kwargs, now=datetime(2026, 10, 1, 0, tzinfo=timezone.utc))
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = State(str(Path(self.temp.name) / "state.db"))
        self.payload = {"recipient": "recipient@example.test", "subject": "测试", "text": "text", "html": "<p>text</p>", "aliases": ["doi:10.9999/test"], "harvest_until": "2026-10-01"}
        self.payload["analysis_policy"] = "required-v1"
        self.state.prepare("test-id", self.payload)
        self.c = copy.deepcopy(DEFAULTS); self.c["mail"]["enabled"] = True
        enable_model(self, self.c)
        self.env = patch.dict(os.environ, {"LITERATURE_SMTP_HOST": "smtp.example.test", "LITERATURE_SMTP_USER": "test", "LITERATURE_SMTP_PASSWORD": "synthetic-test-only", "LITERATURE_MAIL_FROM": "sender@example.test"})
        self.env.start()
    def tearDown(self): self.env.stop(); self.state.close(); self.temp.cleanup()
    def test_old_outbox_cannot_bypass_freshness(self):
        old = {**self.payload, "harvest_until": "2026-09-30"}
        with self.assertRaises(MailSetupError): self.send(old, self.c, self.state, "test-id")
    def test_connection_failure_remains_prepared(self):
        def fail(*a, **k): raise OSError("test")
        with self.assertRaises(MailSetupError): self.send(self.payload, self.c, self.state, "test-id", smtp_ssl=fail)
        self.assertEqual(self.state.get("test-id")["status"], "prepared")
    def test_send_exception_is_uncertain(self):
        class Fake:
            def __init__(self,*a,**k): pass
            def login(self,*a): pass
            def send_message(self,*a,**k): raise OSError("lost after DATA")
            def quit(self): pass
        with self.assertRaises(DeliveryUncertain): self.send(self.payload, self.c, self.state, "test-id", smtp_ssl=Fake)
        self.assertEqual(self.state.get("test-id")["status"], "uncertain")
        self.assertIsNone(self.state.checkpoint())
    def test_quit_failure_after_accept_not_duplicate(self):
        class Fake:
            def __init__(self,*a,**k): pass
            def login(self,*a): pass
            def send_message(self,*a,**k): return {}
            def quit(self): raise OSError("quit failed")
            def close(self): pass
        self.send(self.payload, self.c, self.state, "test-id", smtp_ssl=Fake)
        self.assertEqual(self.state.get("test-id")["status"], "sent")
        self.assertEqual(self.state.checkpoint(), "2026-10-01")
    def test_checkpoint_is_monotonic(self):
        newer = {**self.payload, "harvest_until": "2026-10-03", "aliases": []}
        self.state.prepare("newer", newer); self.state.mark_sent("newer")
        self.state.mark_sent("test-id")
        self.assertEqual(self.state.checkpoint(), "2026-10-03")
    def test_stale_payload_prevents_duplicate(self):
        self.state.prepare("newer", self.payload); self.state.mark_sent("newer")
        with self.assertRaises(MailSetupError):
            self.send(self.payload, self.c, self.state, "test-id")
    def test_resolve_requires_uncertain(self):
        with self.assertRaises(ValueError): self.state.resolve("test-id", "retry")
        self.state.status("test-id", "uncertain")
        self.state.resolve("test-id", "sent")
        self.assertEqual(self.state.get("test-id")["status"], "sent")


if __name__ == "__main__": unittest.main()

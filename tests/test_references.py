"""Offline citation export and MIME tests; all records and transport are synthetic."""
import copy
import hashlib
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from literature_digest.analysis import ANALYSIS_POLICY
from literature_digest.config import DEFAULTS
from literature_digest.mail import MailSetupError, send_smtp
from literature_digest.models import Paper
from literature_digest.pipeline import run, verify_payload_config
from literature_digest.references import bibtex, reference_files, ris, validate_reference_files
from literature_digest.relevance import merge_papers
from literature_digest.sources import crossref_paper, epmc_paper
from literature_digest.state import State, state_scope
from model_fixture import enable_model, install_model_double


def fixture(identifier="selected", day="2026-10-01", **kwargs):
    fields = dict(title="SYNTHETIC forest BVOC emissions and tree species mapping using lidar",
                  source_id=identifier, source="test", url="https://example.org/" + identifier,
                  abstract="Synthetic fixture evidence only; not a real research publication.",
                  authors=["María de la Cruz", "王小明"], journal="Synthetic journal",
                  publication_date=day, publication_date_label="Synthetic fixed date",
                  tracks=["bvoc", "tree_species"],
                  provenance=[{"date_fields": {"published-online": {"date-parts": [[int(v) for v in day.split('-')]]}}}])
    fields.update(kwargs)
    return Paper(**fields)


def parse_ris(text):
    """Small strict structure validator independent of the production serializer."""
    records, current = [], None
    for line in text.splitlines():
        if not line:
            continue
        match = re.fullmatch(r"([A-Z0-9]{2})  - ?(.*)", line)
        if not match:
            raise AssertionError("Malformed RIS line: " + line)
        tag, value = match.groups()
        if tag == "TY":
            if current is not None:
                raise AssertionError("Nested RIS record")
            current = {"TY": [value]}
        elif tag == "ER":
            if current is None:
                raise AssertionError("Unexpected end record")
            records.append(current)
            current = None
        else:
            if current is None:
                raise AssertionError("RIS tag outside record")
            current.setdefault(tag, []).append(value)
    if current is not None:
        raise AssertionError("Unterminated record")
    return records


def parse_bib(text):
    """Validate entry/field structure including nesting and escaped braces."""
    result, offset = [], 0
    while text[offset:].strip():
        match = re.match(r"\s*@([a-z]+)\{([a-zA-Z0-9_]+),\s*", text[offset:])
        if not match:
            raise AssertionError("Malformed BibTeX entry")
        offset += match.end()
        entry = {"ENTRYTYPE": match[1], "ID": match[2]}
        while text[offset] != "}":
            field = re.match(r"([a-zA-Z]+) = \{", text[offset:])
            if not field:
                raise AssertionError("Malformed field: " + text[offset:offset + 40])
            offset += field.end()
            start, depth = offset, 1
            while depth:
                # BibTeX balances braces even after a backslash. Escaped lone
                # braces are unsafe; the writer uses balanced textbrace macros.
                depth += (text[offset] == "{") - (text[offset] == "}")
                offset += 1
            entry[field[1]] = text[start:offset - 1]
            separator = re.match(r",?\s*", text[offset:])
            offset += separator.end()
        offset += 1
        result.append(entry)
    return result


class ReferenceFormatTest(unittest.TestCase):
    def test_unicode_quotes_controls_cannot_inject_records_or_fields(self):
        p = fixture(title='树冠 "quote" } @article{evil, title={fake}} \\ 50% & # _ $ ~ ^\nTY  - BOOK\r\nER  - ',
                    authors=["Research and Development Team", "王小明\nAU  - extra"],
                    abstract="第一行\n第二行\r\nER  - \nTY  - JOUR\x00")
        records = parse_ris(ris([p]))
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0]["AU"]), 2)
        self.assertIn('树冠 "quote"', records[0]["TI"][0])
        self.assertNotIn("\x00", ris([p]))
        entries = parse_bib(bibtex([p]))
        self.assertEqual(len(entries), 1)
        self.assertNotEqual(entries[0]["ID"], "evil")
        self.assertIn(r"\textbraceright{}", entries[0]["title"])
        self.assertIn(r"\textbackslash{}", entries[0]["title"])
        self.assertIn(r"\%", entries[0]["title"])
        self.assertIn("{Research and Development Team}", entries[0]["author"])
        self.assertIn("王小明", entries[0]["author"])

    def test_source_names_preserve_structured_surnames_and_corporate_names(self):
        crossref = crossref_paper({"title": ["Synthetic"], "author": [
            {"given": "María", "family": "de la Cruz"}, {"name": "Research and Development Team"}]}, {})
        self.assertEqual(parse_ris(ris([crossref]))[0]["AU"], ["de la Cruz, María", "Research and Development Team"])
        self.assertIn("{de la Cruz}, {María} and {Research and Development Team}", bibtex([crossref]))
        epmc = epmc_paper({"id": "1", "authorList": {"author": [
            {"firstName": "小明", "lastName": "王", "fullName": "王小明"}, {"collectiveName": "Example Consortium"}]}}, {})
        self.assertEqual(parse_ris(ris([epmc]))[0]["AU"], ["王, 小明", "Example Consortium"])

    def test_merge_never_misaligns_source_name_metadata(self):
        first = fixture(authors=["Maria Cruz"])
        second = fixture(authors=["María de la Cruz"], author_details=[{"given": "María", "family": "de la Cruz"}])
        merged = merge_papers([first, second])[0]
        self.assertEqual(merged.authors, ["Maria Cruz"])
        self.assertEqual(merged.author_details, [])
        first = fixture(authors=[])
        merged = merge_papers([first, second])[0]
        self.assertEqual(merged.author_details, second.author_details)

    def test_partial_missing_metadata_does_not_invent_doi_date_or_authors(self):
        p = fixture(authors=[], journal="", publication_date="2026", doi="", url="")
        record = parse_ris(ris([p]))[0]
        entry = parse_bib(bibtex([p]))[0]
        self.assertEqual(record["DA"], ["2026"])
        self.assertEqual(entry["date"], "2026")
        for tag in ("DO", "JO", "UR", "AU"):
            self.assertNotIn(tag, record)
        for key in ("doi", "journal", "url", "author"):
            self.assertNotIn(key, entry)
        p.publication_date, p.doi, p.url = "2026-02-30", "not-a-doi\nDO  - injected", "javascript:alert(1)"
        record = parse_ris(ris([p]))[0]
        self.assertNotIn("DA", record)
        self.assertNotIn("DO", record)
        self.assertNotIn("UR", record)

    def test_doi_original_url_and_full_author_list_are_retained(self):
        p = fixture(doi="HTTPS://doi.org/10.9999/Synthetic_Test", authors=["Author " + str(i) for i in range(12)])
        record = parse_ris(ris([p]))[0]
        self.assertEqual(record["DO"], ["10.9999/synthetic_test"])
        self.assertEqual(record["UR"], [p.url])
        self.assertEqual(len(record["AU"]), 12)
        self.assertIn(r"10.9999/synthetic\_test", bibtex([p]))

    def test_duplicate_cross_track_reference_is_exported_once(self):
        p = fixture()
        self.assertEqual(len(parse_ris(ris([p, copy.deepcopy(p)]))), 1)
        self.assertEqual(len(parse_bib(bibtex([p, copy.deepcopy(p)]))), 1)
        self.assertEqual(len(parse_ris(ris([p, fixture("different")]))), 2)

    def test_preprint_and_synthetic_not_claimed_as_journal_articles(self):
        for source, expected in (("demo", "GEN"), ("arxiv", "UNPB")):
            p = fixture(source=source, doi="")
            self.assertEqual(parse_ris(ris([p]))[0]["TY"], [expected])
            self.assertEqual(parse_bib(bibtex([p]))[0]["ENTRYTYPE"], "misc")
        self.assertIn("DEMO / SYNTHETIC", ris([fixture(source="demo")]))
        self.assertIn("DEMO / SYNTHETIC", bibtex([fixture(source="demo")]))

    def test_snapshot_is_stable_validated_and_no_empty_exports(self):
        files = reference_files([fixture()], "2026-10-03_issue_preview")
        self.assertEqual(files, reference_files([fixture()], "2026-10-03_issue_preview"))
        self.assertEqual(validate_reference_files(files), files)
        self.assertEqual(reference_files([], "empty"), [])
        corrupted = copy.deepcopy(files)
        corrupted[0]["content"] += "tampering"
        with self.assertRaises(ValueError):
            validate_reference_files(corrupted)
        with self.assertRaises(ValueError):
            reference_files([fixture()], "../unsafe")


class PipelineReferenceTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.c = copy.deepcopy(DEFAULTS)
        self.c.update(state_path=str(Path(directory.name) / "state.db"), output_dir=str(Path(directory.name) / "output"), sources=["crossref"], fetch_full_text=False)
        self.now = datetime(2026, 10, 3, 8, tzinfo=timezone.utc)
        install_model_double(self, self.c)

    def fetcher(self, papers):
        return {"crossref": lambda *args: (copy.deepcopy(papers), {"source": "crossref", "complete": True})}

    def test_only_selected_deduplicated_papers_in_real_run_sidecars(self):
        self.c["max_papers_per_track"] = 1
        papers = [fixture("selected", day="2026-10-02"), fixture("selected", day="2026-10-02"),
                  fixture("old", day="2026-09-01"), fixture("deferred", day="2026-10-01"),
                  fixture("unrelated", title="Synthetic industrial manufacturing only", abstract=" unrelated")]
        result = run(self.c, now=self.now, fetchers=self.fetcher(papers))
        self.assertEqual(result["paper_count"], 1)
        audit = json.loads(Path(result["paths"]["json"]).read_text(encoding="utf-8"))
        self.assertEqual(audit["meta"]["deferred"], 1)
        for manifest in audit["meta"]["reference_exports"]:
            content = Path(result["paths"][manifest["format"]]).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), manifest["sha256"])
            self.assertEqual(manifest["paper_count"], 1)
        self.assertEqual(parse_ris(Path(result["paths"]["ris"]).read_text(encoding="utf-8"))[0]["UR"], ["https://example.org/selected"])
        html = Path(result["paths"]["html"]).read_text(encoding="utf-8")
        self.assertIn('download href="' + Path(result["paths"]["ris"]).name + '"', html)
        self.assertNotIn("file:", html)

    def test_empty_issue_has_no_downloads_or_stale_sidecars(self):
        initial = run(self.c, now=self.now, fetchers=self.fetcher([fixture()]))
        empty = run(self.c, now=self.now, fetchers=self.fetcher([]))
        self.assertEqual(empty["paper_count"], 0)
        self.assertNotIn("ris", empty["paths"])
        self.assertNotIn("bib", empty["paths"])
        self.assertFalse(Path(initial["paths"]["ris"]).exists())
        self.assertFalse(Path(initial["paths"]["bib"]).exists())
        self.assertNotIn("download href", Path(empty["paths"]["html"]).read_text(encoding="utf-8"))

    def test_prepared_retry_uses_snapshot_not_modified_disk_and_rejects_changed_settings(self):
        captured = []
        def fail(payload, *args):
            captured.append(copy.deepcopy(payload))
            raise MailSetupError("Offline simulated SMTP pre-DATA failure")
        with self.assertRaises(MailSetupError):
            run(self.c, send=True, now=self.now, fetchers=self.fetcher([fixture()]), mail_adapter=fail)
        prepared = captured[0]
        for extension in ("ris", "bib"):
            Path(prepared["paths"][extension]).write_text("changed local sidecar")
        changed = copy.deepcopy(self.c)
        changed["language"] = "en"
        with self.assertRaises(ValueError):
            verify_payload_config(prepared, changed)
        def accept(payload, config, state, digest_id):
            self.assertEqual(payload["reference_files"], prepared["reference_files"])
            self.assertNotIn("download href", payload["html"])
            self.assertIn("本邮件已附上", payload["html"])
            state.mark_sent(digest_id)
        result = run(self.c, send=True, now=self.now, fetchers={"crossref": lambda *a: self.fail("retry refetched sources")}, mail_adapter=accept)
        self.assertTrue(result["reused_prepared_outbox"])


class ReferenceMailTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.c = copy.deepcopy(DEFAULTS)
        self.c["mail"]["enabled"] = True
        enable_model(self, self.c)
        context = patch.dict(os.environ, {"LITERATURE_SMTP_HOST": "smtp.example.test", "LITERATURE_SMTP_USER": "synthetic", "LITERATURE_SMTP_PASSWORD": "synthetic-test-only", "LITERATURE_MAIL_FROM": "sender@example.org"})
        context.start()
        self.addCleanup(context.stop)
        self.state = State(str(Path(directory.name) / "state.db"), state_scope(self.c))
        self.addCleanup(self.state.close)
        self.payload = {"recipient": self.c["recipient"], "subject": "Synthetic export test", "text": "body", "html": "<p>body</p>",
                        "harvest_until": "2026-10-03", "aliases": ["test:selected"], "analysis_policy": ANALYSIS_POLICY,
                        "reference_files": reference_files([fixture()], "2026-10-03_test")}
        self.state.prepare("test", self.payload)

    def test_mime_attachments_contain_exact_utf8_snapshot_bytes(self):
        captured = []
        class FakeSMTP:
            def __init__(self, *args, **kwargs): pass
            def login(self, *args): pass
            def send_message(self, message, **kwargs):
                captured.append(message)
                return {}
            def quit(self): pass
        send_smtp(self.payload, self.c, self.state, "test", smtp_ssl=FakeSMTP, now=datetime(2026, 10, 3, tzinfo=timezone.utc))
        self.assertEqual(captured[0].get_content_type(), "multipart/mixed")
        attachments = list(captured[0].iter_attachments())
        self.assertEqual(len(attachments), 2)
        for attachment, expected in zip(attachments, self.payload["reference_files"]):
            self.assertEqual(attachment.get_filename(), expected["filename"])
            self.assertEqual(attachment.get_content_type(), expected["content_type"])
            self.assertEqual(attachment.get_payload(decode=True), expected["content"].encode("utf-8"))
        self.assertEqual(self.state.get("test")["status"], "sent")

    def test_corrupt_attachment_stops_before_smtp(self):
        self.payload["reference_files"][0]["content"] += "modified"
        with self.assertRaises(MailSetupError):
            send_smtp(self.payload, self.c, self.state, "test", smtp_ssl=lambda *a, **k: self.fail("SMTP attempted"), now=datetime(2026, 10, 3, tzinfo=timezone.utc))
        self.assertEqual(self.state.get("test")["status"], "prepared")


if __name__ == "__main__":
    unittest.main()

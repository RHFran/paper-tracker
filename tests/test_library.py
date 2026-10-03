"""Offline tests of durable, audience-scoped literature metadata."""
import json
import tempfile
import unittest
from pathlib import Path

from literature_digest.library import export_papers, list_papers, save_papers
from literature_digest.models import Paper
from literature_digest.references import validate_reference_files
from literature_digest.state import State, state_scope


def fixture(identifier="one", **kwargs):
    values = dict(title="SYNTHETIC Straße 树种 research", source_id=identifier,
                  source="fixture", url="https://example.org/" + identifier,
                  authors=["María de la Cruz", "王小明"], journal="Synthetic Journal",
                  abstract="Only synthetic evidence about forest emissions.",
                  publication_date="2026-10-03", tracks=["tree_species"],
                  full_text="PRIVATE FULL TEXT MUST NOT ENTER THE LIBRARY",
                  analysis={"mode": "llm_grounded", "fields": {"summary": ["Synthetic analysis"]}},
                  provenance=[{"source": "fixture", "retrieved_at": "2026-10-03"}])
    values.update(kwargs)
    return Paper(**values)


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.sqlite"
        self.state = self.open_state()

    def open_state(self, profile="primary", recipient="reader@example.org"):
        state = State(self.path, scope=state_scope({"profile_id": profile, "recipient": recipient}))
        self.addCleanup(state.close)
        return state

    def save(self, paper=None, digest="issue-1", paths=None, state=None):
        paper = paper or fixture()
        save_papers(state or self.state, [paper], digest, paths or {"json": "/reports/issue-1.json"})
        return paper

    def test_empty_library_and_exports_are_safe_and_lazy(self):
        self.assertEqual(list_papers(self.state), [])
        self.assertEqual(export_papers(self.state), [])
        self.assertIsNone(self.state.checkpoint())

    def test_persists_metadata_analysis_provenance_without_full_text(self):
        paper = self.save()
        result = list_papers(self.open_state())[0]
        self.assertEqual(result["analysis"], paper.analysis)
        self.assertEqual(result["provenance"], paper.provenance)
        self.assertEqual(result["source"], "fixture")
        self.assertEqual(result["last_digest"], "issue-1")
        self.assertEqual(result["audit_path"], "/reports/issue-1.json")
        self.assertEqual(result["aliases"], paper.aliases)
        self.assertNotIn("full_text", result)
        self.assertNotIn(paper.full_text, json.dumps(result))
        self.assertNotIn("config", result)
        self.assertEqual(result["evidence_sha256"], paper.export()["evidence_sha256"])
        self.assertEqual(paper.source_aliases, [])  # Saving cannot mutate pipeline objects.

    def test_profile_and_recipient_are_both_isolated(self):
        self.save()
        for isolated in (self.open_state(profile="other"),
                         self.open_state(recipient="other@example.org")):
            self.assertEqual(list_papers(isolated), [])
            self.assertEqual(export_papers(isolated), [])
            self.save(fixture(title="Separate audience record"), state=isolated)
            self.assertEqual(list_papers(isolated)[0]["title"], "Separate audience record")
        self.assertIn("Straße", list_papers(self.state)[0]["title"])
        self.assertEqual(len(list_papers(self.open_state(recipient="READER@example.org"))), 1)

    def test_upsert_keeps_aliases_and_identifiers_with_latest_source(self):
        first = self.save(fixture(doi="10.9999/example", pmcid="PMC123"))
        replacement = fixture("two", source="new_source", doi="", pmcid="PMC123",
                              title="Updated metadata", analysis={"updated": True})
        self.save(replacement, digest="issue-2", paths={"audit": Path("/reports/two/audit.json")})
        self.save(replacement, digest="issue-2", paths={"audit": "/reports/two/audit.json"})
        result, = list_papers(self.state)
        self.assertEqual(result["title"], "Updated metadata")
        self.assertEqual(result["analysis"], {"updated": True})
        self.assertEqual(result["source"], "new_source")
        self.assertEqual(result["source_id"], "two")
        self.assertEqual(result["doi"], first.doi)
        self.assertEqual(result["key"], first.key)
        self.assertTrue(set(first.aliases + replacement.aliases) <= set(result["aliases"]))
        self.assertEqual(result["last_digest"], "issue-2")
        self.assertEqual(result["audit_path"], "/reports/two/audit.json")
        self.assertEqual(self.state.db.execute("SELECT count(*) FROM library_papers_v1").fetchone()[0], 1)

    def test_snapshot_associations_are_immutable(self):
        original = self.save()
        self.save(fixture(title="Replacement"))
        row = self.state.db.execute(
            "SELECT metadata,audit_path FROM library_digest_papers_v1 "
            "WHERE scope=? AND digest_id=? AND paper_key=?",
            (self.state.scope, "issue-1", original.key)).fetchone()
        self.assertEqual(json.loads(row[0])["title"], original.title)
        self.assertEqual(row[1], "/reports/issue-1.json")
        self.assertNotIn("full_text", json.loads(row[0]))
        self.assertEqual(list_papers(self.state)[0]["audit_path"], row[1])
        self.assertEqual(list_papers(self.state)[0]["title"], "Replacement")

    def test_preview_and_final_paths_keep_separate_immutable_associations(self):
        original = self.save(paths={"json": "/reports/issue-1_preview.json"})
        final = fixture(title="Final selected metadata")
        self.save(final, paths={"audit": "/reports/connector/issue-1/audit.json"})
        self.save(fixture(title="Later metadata"),
                  paths={"audit": "/reports/connector/issue-1/audit.json"})
        rows = self.state.db.execute(
            "SELECT audit_path,metadata FROM library_digest_papers_v1 "
            "WHERE scope=? AND digest_id=? AND paper_key=? ORDER BY audit_path",
            (self.state.scope, "issue-1", original.key)).fetchall()
        snapshots = {path: json.loads(raw) for path, raw in rows}
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots["/reports/issue-1_preview.json"]["title"], original.title)
        self.assertEqual(snapshots["/reports/connector/issue-1/audit.json"]["title"], final.title)
        result, = list_papers(self.state)
        self.assertEqual(result["title"], "Later metadata")
        self.assertEqual(result["audit_path"], "/reports/connector/issue-1/audit.json")
        self.assertEqual(result["last_digest"], "issue-1")

    def test_alias_bridge_merges_rows_without_losing_earlier_digests(self):
        first = self.save(fixture("first", doi="10.9999/first"), digest="first-digest")
        second = self.save(fixture("second", pmcid="PMC234"), digest="second-digest")
        self.assertEqual(len(list_papers(self.state)), 2)
        bridge = fixture("third", doi=first.doi, pmcid=second.pmcid)
        self.save(bridge, digest="third-digest")
        result, = list_papers(self.state)
        self.assertTrue(set(first.aliases + second.aliases + bridge.aliases) <= set(result["aliases"]))
        self.assertEqual(self.state.db.execute("SELECT count(*) FROM library_digest_papers_v1").fetchone()[0], 3)
        # All old aliases still resolve to the merged record on a later update.
        self.save(second, digest="fourth-digest")
        self.assertEqual(len(list_papers(self.state)), 1)

    def test_same_title_without_shared_identity_is_not_deduplicated(self):
        save_papers(self.state, [fixture("one"), fixture("two")], "issue", {})
        self.assertEqual(len(list_papers(self.state)), 2)

    def test_library_never_marks_delivery_or_advances_checkpoint(self):
        paper = self.save()
        self.assertFalse(self.state.was_sent(paper))
        self.assertIsNone(self.state.checkpoint())
        self.assertEqual(self.state.recent(), [])
        self.state.prepare("issue-1", {"aliases": paper.aliases, "harvest_until": "2026-10-03"})
        self.state.status("issue-1", "uncertain")
        self.assertEqual(len(list_papers(self.state)), 1)
        self.assertFalse(self.state.was_sent(paper))
        self.state.mark_sent("issue-1")
        self.assertEqual(len(list_papers(self.state)), 1)
        self.assertEqual(len(export_papers(self.state)), 2)

    def test_search_is_unicode_casefolded_literal_and_limited_after_matching(self):
        self.save()
        for query in ("STRASSE", "树种", "王小明", "MARÍA", "MARI\u0301A", "EMISSIONS"):
            with self.subTest(query=query):
                self.assertEqual(len(list_papers(self.state, query)), 1)
        for query in ("%", "_", "' OR 1=1 --", "missing"):
            self.assertEqual(list_papers(self.state, query), [])
        self.save(fixture("newer", title="Other research", abstract="No match", authors=[]))
        self.assertEqual(len(list_papers(self.state, "STRASSE", limit=1)), 1)
        self.assertEqual(len(list_papers(self.state, limit=1)), 1)
        self.assertEqual(list_papers(self.state, limit=0), [])
        self.assertEqual(len(list_papers(self.state, "  ")), 2)

    def test_invalid_query_and_limit_fail_clearly(self):
        for limit in (-1, True, "3", 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                list_papers(self.state, limit=limit)
        with self.assertRaises(ValueError):
            list_papers(self.state, query=123)
        with self.assertRaises(ValueError):
            save_papers(self.state, [fixture()], "", {})

    def test_exports_reuse_safe_serializers_and_filter_index_only_fields(self):
        title = "树种 } @article{injected, title={fake}}\nTY  - BOOK\r\nER  - "
        self.save(fixture(title=title, authors=["王小明\nAU  - injected"],
                          abstract="Synthetic\x00 evidence", url="javascript:alert(1)"))
        files = export_papers(self.state, query="树种")
        self.assertEqual(validate_reference_files(files), files)
        self.assertEqual({item["filename"] for item in files}, {"library.ris", "library.bib"})
        ris, bib = [item["content"] for item in files]
        self.assertEqual(sum(line.startswith("TY  - ") for line in ris.splitlines()), 1)
        self.assertEqual(sum(line.startswith("ER  - ") for line in ris.splitlines()), 1)
        self.assertEqual(sum(line.startswith("AU  - ") for line in ris.splitlines()), 1)
        self.assertIn(r"\textbraceright{}", bib)
        self.assertEqual(sum(line.startswith("@") for line in bib.splitlines()), 1)
        for body in (ris, bib):
            self.assertNotIn("\x00", body)
            self.assertNotIn("javascript:", body)
            self.assertNotIn("PRIVATE FULL TEXT", body)
        self.assertEqual(export_papers(self.state, query="missing"), [])

    def test_export_includes_all_results_beyond_default_page(self):
        save_papers(self.state, [fixture(str(index)) for index in range(55)], "large", {})
        self.assertEqual(len(list_papers(self.state)), 50)
        self.assertEqual(len(list_papers(self.state, limit=None)), 55)
        self.assertEqual([item["paper_count"] for item in export_papers(self.state)], [55, 55])

    def test_failed_batch_rolls_back_library_changes(self):
        with self.assertRaises(AttributeError):
            save_papers(self.state, [fixture(), object()], "broken", {})
        self.assertEqual(list_papers(self.state), [])
        self.assertEqual(self.state.db.execute("SELECT count(*) FROM library_digest_papers_v1").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

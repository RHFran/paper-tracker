"""Standalone/API six-section generation; all model responses are synthetic."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from literature_digest.analysis import (analyze, compose_outlook, reference_map,
                                        validate_analysis, validate_live_analysis)
from literature_digest.config import DEFAULTS
from literature_digest.model_backends import ANALYSIS_SCHEMA, OUTLOOK_SCHEMA
from literature_digest.outlook import checked_outlook
from literature_digest.pipeline import config_fingerprint, digest_id, run
from literature_digest.state import State, state_scope
from model_fixture import outlook_fixture, perspective_fixture
from test_editorial import ANCHOR_A, ANCHOR_B, FakeHttp, cfg, fixture_paper
from test_required_llm import ENV, ReviewModel, EVIDENCE


def current_paper(number=1, language="en"):
    paper = fixture_paper(number, language)
    anchor = ANCHOR_A if number == 1 else ANCHOR_B
    paper.analysis["fields"]["methods"] = [{"text": "合成实验采用受控方法。" if language.startswith("zh") else
                                           "The synthetic experiment uses controlled methods.", "evidence": anchor}]
    paper.analysis["perspective"] = perspective_fixture(anchor, language)
    return paper


class StandaloneOutlook(unittest.TestCase):
    def setUp(self):
        self.papers = [current_paper(), current_paper(2)]
        self.config = cfg()
        self.config["llm"]["enabled"] = True
        environment = patch.dict(os.environ, {"TEST_EDITORIAL_BASE": "https://model.example.org/v1",
                                              "TEST_EDITORIAL_KEY": "synthetic-token",
                                              "TEST_EDITORIAL_MODEL": "fixture"})
        environment.start(); self.addCleanup(environment.stop)
        network = patch("literature_digest.http.HttpClient.request", side_effect=AssertionError("No real network"))
        network.start(); self.addCleanup(network.stop)

    def data(self, language="en"):
        return outlook_fixture([{"ref": 1, "evidence": ANCHOR_A}, {"ref": 2, "evidence": ANCHOR_B}], language)

    def test_live_schema_adds_perspective_without_changing_frozen_field_schema(self):
        paper = self.papers[0]
        data = {key: paper.analysis[key] for key in ("fields", "perspective")}
        self.assertEqual(validate_live_analysis(data, paper.evidence, "en"), data)
        self.assertEqual(validate_analysis(data["fields"], paper.evidence, "en"), data["fields"])
        for mutation in ("old", "question", "methods", "result", "perspective", "kind", "anchor"):
            changed = copy.deepcopy(data)
            if mutation == "old": changed = changed["fields"]
            elif mutation in ("question", "methods"): changed["fields"][mutation] = []
            elif mutation == "result": changed["fields"].update(findings=[], highlights=[])
            elif mutation == "perspective": changed["perspective"]["limitations"] = []
            elif mutation == "kind": changed["perspective"]["limitations"][0]["kind"] = "established"
            elif mutation == "anchor": changed["perspective"]["limitations"][0]["evidence"] = ANCHOR_B
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_live_analysis(changed, paper.evidence, "en")

    def test_highlight_may_supply_results_block_without_fabricated_finding(self):
        data = {key: copy.deepcopy(self.papers[0].analysis[key]) for key in ("fields", "perspective")}
        data["fields"]["findings"] = []
        self.assertTrue(validate_live_analysis(data, self.papers[0].evidence, "en")["fields"]["highlights"])

    def test_new_api_analysis_rejects_old_model_response(self):
        result = analyze(self.papers[0], self.config, FakeHttp(self.papers[0].analysis["fields"]))
        self.assertEqual(result["mode"], "discovery_only")

    def test_composition_preserves_reference_order_and_declares_interpretations(self):
        http = FakeHttp(self.data())
        result = compose_outlook(self.papers, self.config, http)
        self.assertEqual(result["mode"], "llm_grounded")
        self.assertIsNotNone(checked_outlook(result, self.papers, "en"))
        self.assertEqual(result["references"], reference_map(self.papers))
        messages = http.calls[0][1]["payload"]["messages"]
        content = json.loads(messages[1]["content"])
        self.assertEqual([p["ref"] for p in content["untrusted_outlook_papers"]], [1, 2])
        self.assertEqual(content["untrusted_outlook_papers"][0]["grounded_perspective"]["limitations"][0]["kind"], "inferred")
        for word in ("falsifiable", "comparator", "conditional", "untrusted"):
            self.assertIn(word, messages[0]["content"])

    def test_configured_language_is_used_for_analysis_and_outlook(self):
        for language in ("en", "zh-CN"):
            papers = [current_paper(1, language), current_paper(2, language)]
            config = copy.deepcopy(self.config); config["language"] = language
            http = FakeHttp(self.data(language))
            result = compose_outlook(papers, config, http)
            self.assertEqual(result["mode"], "llm_grounded")
            self.assertEqual(result["language"], language)
            content = json.loads(http.calls[0][1]["payload"]["messages"][1]["content"])
            self.assertEqual(content["output_language"], language)
            data = {key: papers[0].analysis[key] for key in ("fields", "perspective")}
            self.assertEqual(analyze(papers[0], config, FakeHttp(data))["mode"], "llm_grounded")

    def test_unseen_source_quote_is_rejected_in_every_cited_outlook_component(self):
        unseen = "An additional synthetic observation not supplied to the model."
        self.papers[0].abstract += " " + unseen
        for component in ("synthesis", "open_questions", "basis"):
            data = self.data()
            statements = (data["synthesis"]["paragraphs"][0]["sentences"] if component == "synthesis" else
                          data["open_questions"] if component == "open_questions" else data["ideas"][0]["basis"])
            statements[0]["citations"][0]["evidence"] = unseen
            with self.subTest(component=component):
                result = compose_outlook(self.papers, self.config, FakeHttp(data))
                self.assertEqual(result["mode"], "unavailable")
                self.assertNotIn("ideas", result)

    def test_outlook_failure_has_no_generated_fallback_or_raw_provider_data(self):
        http = FakeHttp({"secret-provider-text": "never repeat this"})
        result = compose_outlook(self.papers, self.config, http)
        self.assertEqual(result["mode"], "unavailable")
        self.assertNotIn("ideas", result)
        self.assertNotIn("never repeat", json.dumps(result))

    def test_all_selected_papers_must_have_grounded_current_analysis(self):
        for field in ("mode", "perspective"):
            papers = copy.deepcopy(self.papers)
            if field == "mode": papers[1].analysis["mode"] = "discovery_only"
            else: papers[1].analysis.pop("perspective")
            http = FakeHttp(self.data())
            with self.subTest(field=field):
                self.assertEqual(compose_outlook(papers, self.config, http)["mode"], "unavailable")
                self.assertEqual(http.calls, [])

    def test_small_budget_stops_before_closing_call_without_dropping_papers(self):
        self.config["llm"]["max_overview_chars"] = 100
        http = FakeHttp(self.data())
        result = compose_outlook(self.papers, self.config, http)
        self.assertEqual(result["reason"], "evidence_budget_exceeded")
        self.assertEqual(http.calls, [])
        self.assertIn("llm.max_overview_chars", result["warnings"][0])

    def test_empty_selection_calls_no_model_and_has_no_ideas(self):
        http = FakeHttp(self.data())
        result = compose_outlook([], self.config, http)
        self.assertEqual(result["mode"], "empty")
        self.assertEqual(result["ideas"], [])
        self.assertEqual(http.calls, [])

    def test_cli_dispatches_distinct_current_analysis_and_outlook_schemas(self):
        self.config["llm"]["backend"] = "codex"
        analysis = {key: self.papers[0].analysis[key] for key in ("fields", "perspective")}
        with patch("literature_digest.analysis.require_llm", return_value=("codex", "/synthetic/codex", "fixture")), \
             patch("literature_digest.model_backends.cli_request", side_effect=[(analysis, "fixture"), (self.data(), "fixture")]) as model:
            self.assertEqual(analyze(self.papers[0], self.config, None)["mode"], "llm_grounded")
            self.assertEqual(compose_outlook(self.papers, self.config, None)["mode"], "llm_grounded")
        self.assertEqual(model.call_args_list[0].args[3], ANALYSIS_SCHEMA)
        self.assertEqual(model.call_args_list[1].args[3], OUTLOOK_SCHEMA)


class StandalonePipelineOutlook(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = copy.deepcopy(DEFAULTS)
        self.config.update(timezone="UTC", language="en", sources=["crossref"],
            topics=[{"id": "battery", "name": "Battery", "queries": ["battery"]}],
            state_path=str(Path(temporary.name) / "state.db"), output_dir=str(Path(temporary.name) / "output"))
        self.config["llm"]["enabled"] = True
        self.now = datetime(2026, 10, 5, 9, tzinfo=timezone.utc)
        self.paper = current_paper()
        self.paper.title = "Synthetic battery study"
        self.paper.abstract = EVIDENCE
        self.paper.provenance = [{"date_fields": {"published-online": {"date-parts": [[2026, 10, 5]]}}}]
        self.fetchers = {"crossref": lambda *args: ([self.paper], {"complete": True})}
        context = patch.dict(os.environ, ENV, clear=True)
        context.start(); self.addCleanup(context.stop)

    def test_connector_audit_and_envelope_include_validated_outlook(self):
        model = ReviewModel()
        result = run(self.config, now=self.now, http=model, fetchers=self.fetchers, prepare_connector=True)
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(len(model.calls), 3)
        audit = json.loads(Path(result["paths"]["audit"]).read_text(encoding="utf-8"))
        envelope = json.loads(Path(result["paths"]["envelope"]).read_text(encoding="utf-8"))
        self.assertEqual(audit["outlook"]["mode"], "llm_grounded")
        for heading in ("Problem and design", "Scientific question", "Method chain", "Results and highlights", "Limitations", "Research implications"):
            self.assertEqual(envelope["text"].count(heading + ":"), 1)
        self.assertIn("Closing synthesis and research outlook", envelope["html"])
        self.assertIn("Synthetic input sensitivity test", envelope["text"])

    def test_outlook_failure_pauses_paid_retry_without_output_or_delivery(self):
        model = ReviewModel("outlook_failure")
        with self.assertRaisesRegex(RuntimeError, "closing research outlook.*paused"):
            run(self.config, now=self.now, http=model, fetchers=self.fetchers, prepare_connector=True)
        self.assertEqual(len(model.calls), 3)
        state = State(self.config["state_path"], scope=state_scope(self.config))
        try:
            self.assertIsNotNone(state.model_failure_pause())
            self.assertEqual(state.recent(), [])
        finally:
            state.close()
        self.assertFalse(Path(self.config["output_dir"]).exists())

    def test_closing_budget_error_discloses_prior_usage_and_skips_only_closing_call(self):
        self.config["llm"]["max_overview_chars"] = 1000
        model = ReviewModel()
        with self.assertRaisesRegex(RuntimeError, "llm.max_overview_chars.*earlier model stages consumed usage"):
            run(self.config, now=self.now, http=model, fetchers=self.fetchers)
        self.assertEqual(len(model.calls), 2)
        self.assertFalse(Path(self.config["output_dir"]).exists())

    def test_frozen_legacy_verified_outbox_is_reused_without_new_model_call(self):
        identifier = digest_id(self.config, self.now.date())
        payload = {"analysis_policy": "required-v1", "recipient": self.config["recipient"],
                   "config_fingerprint": config_fingerprint(self.config), "reference_files": [],
                   "text": "Frozen legacy verified report", "html": "<p>Frozen legacy verified report</p>",
                   "aliases": [], "harvest_until": self.now.date().isoformat(), "paths": {}}
        state = State(self.config["state_path"], scope=state_scope(self.config))
        state.prepare(identifier, payload); state.close()
        model, sent = ReviewModel(), []
        def mail(saved, config, state, identifier):
            sent.append(saved)
            state.mark_sent(identifier)
        result = run(self.config, send=True, now=self.now, http=model, fetchers=self.fetchers, mail_adapter=mail)
        self.assertTrue(result["reused_prepared_outbox"])
        self.assertEqual(sent, [payload])
        self.assertEqual(model.calls, [])


if __name__ == "__main__":
    unittest.main()

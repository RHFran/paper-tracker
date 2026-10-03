"""Persistent automatic-retry cost guard; no elapsed waits or provider requests."""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from literature_digest.analysis import ModelAnalysisError
from literature_digest.cli import _many, _run_one, main
from literature_digest.config import DEFAULTS
from literature_digest.models import Paper
from literature_digest.pipeline import run
from literature_digest.state import State, state_scope
from test_required_llm import ENV, EVIDENCE, ReviewModel


class ModelRetryPause(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.config = copy.deepcopy(DEFAULTS)
        self.config.update(timezone="UTC", language="en", sources=["crossref"],
                           state_path=str(self.directory / "state.db"), output_dir=str(self.directory / "output"),
                           topics=[{"id": "battery", "name": "Battery", "queries": ["battery"]}])
        self.config["llm"]["enabled"] = True
        self.now = datetime(2026, 10, 5, 9, tzinfo=timezone.utc)
        environment = patch.dict(os.environ, ENV, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        network = patch("literature_digest.http.HttpClient.request", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)
        self.model = ReviewModel("overview_failure")
        self.retrievals = 0

        def fetch(*args):
            self.retrievals += 1
            return ([Paper(title="Synthetic battery study", source="crossref", source_id="test", url="https://example.org/test",
                           doi="10.9999/pause", abstract=EVIDENCE,
                           provenance=[{"date_fields": {"published-online": {"date-parts": [[2026, 10, 5]]}}}])], {"complete": True})

        def execute(config, **kwargs):
            return run(config, **kwargs, http=self.model, fetchers={"crossref": fetch},
                       mail_adapter=lambda payload, cfg, state, identifier: state.mark_sent(identifier))

        runner = patch("literature_digest.cli.run", side_effect=execute)
        runner.start()
        self.addCleanup(runner.stop)

    def fail_once(self):
        with self.assertRaisesRegex(ModelAnalysisError, "paused"):
            _run_one(self.config, "tick", True, self.now)
        self.assertEqual(len(self.model.calls), 2)

    def read_pause(self):
        state = State(self.config["state_path"], scope=state_scope(self.config))
        try:
            return state.model_failure_pause()
        finally:
            state.close()

    def test_restart_and_repeated_ticks_do_not_repeat_paid_model_calls(self):
        self.fail_once()
        self.assertEqual(self.read_pause()["local_date"], "2026-10-05")
        for hour in (10, 16, 23):
            result = _run_one(copy.deepcopy(self.config), "tick", True, self.now.replace(hour=hour))
            self.assertEqual(result["status"], "model_paused")
            self.assertIn("retry", result["pause"])
        self.assertEqual(len(self.model.calls), 2)
        self.assertEqual(self.retrievals, 1)

    def test_explicit_run_retries_and_success_clears_pause(self):
        self.fail_once()
        self.model = ReviewModel()
        result = _run_one(self.config, "run", False, self.now + timedelta(minutes=1))
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(len(self.model.calls), 3)
        self.assertIsNone(self.read_pause())
        sent = _run_one(self.config, "tick", True, self.now + timedelta(minutes=2))
        repeat = _run_one(self.config, "tick", True, self.now + timedelta(minutes=3))
        self.assertEqual(sent["status"], "sent")
        self.assertEqual(repeat["status"], "already_sent")
        self.assertEqual(len(self.model.calls), 6)

    def test_next_local_day_allows_one_new_attempt(self):
        self.config["timezone"] = "Asia/Shanghai"
        self.now = datetime(2026, 10, 5, 15, tzinfo=timezone.utc)  # 23:00 local.
        self.fail_once()
        self.model = ReviewModel()
        result = _run_one(self.config, "tick", True, datetime(2026, 10, 6, 1, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(self.model.calls), 3)

    def test_other_profile_is_not_paused(self):
        self.fail_once()
        other = copy.deepcopy(self.config)
        other["profile_id"] = "independent-topic"
        self.model = ReviewModel()
        self.assertEqual(_run_one(other, "tick", False, self.now)["status"], "dry_run")
        self.assertIsNotNone(self.read_pause())

    def test_schedule_edit_does_not_bypass_pause_but_model_config_change_does(self):
        self.fail_once()
        self.config["schedule"]["time"] = "08:00"
        self.assertEqual(_run_one(self.config, "tick", True, self.now)["status"], "model_paused")
        self.config["llm"]["model_env"] = "REPLACEMENT_MODEL"
        self.model = ReviewModel()
        with patch.dict(os.environ, {"REPLACEMENT_MODEL": "synthetic-replacement"}):
            self.assertEqual(_run_one(self.config, "tick", False, self.now)["status"], "dry_run")
        self.assertIsNone(self.read_pause())

    def test_foreground_restart_respects_persisted_pause_without_busy_logs(self):
        self.fail_once()
        path = self.directory / "config.json"
        path.write_text(json.dumps(self.config))
        with patch("literature_digest.cli.datetime") as clock, patch("literature_digest.cli._many", side_effect=AssertionError("No retry")), patch("literature_digest.cli.time.sleep", side_effect=KeyboardInterrupt), redirect_stdout(io.StringIO()):
            clock.now.return_value = self.now
            self.assertEqual(main(["--config", str(path), "schedule", "--send"]), 130)
        self.assertEqual(len(self.model.calls), 2)

    def test_multi_profile_failure_does_not_block_other_due_profile(self):
        self.fail_once()
        other = copy.deepcopy(self.config)
        other["profile_id"] = "other"
        self.model = ReviewModel()
        result = _many([self.config, other], "tick", False, self.now)
        self.assertEqual([item["status"] for item in result], ["model_paused", "dry_run"])


if __name__ == "__main__":
    unittest.main()

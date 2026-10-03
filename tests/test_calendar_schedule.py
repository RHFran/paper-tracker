"""Offline contracts for topic calendars, finite dates, and isolated deliveries."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from literature_digest.cli import _many, _run_one, main
from literature_digest.config import DEFAULTS, load_configs
from literature_digest.models import Paper
from literature_digest.pipeline import run
from literature_digest.schedule import is_due, next_run
from model_fixture import install_model_double


def utc(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


class CalendarConfig(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"

    def load(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")
        return load_configs(str(self.path))

    def test_explicit_dates_replace_default_weekdays(self):
        config = self.load({"schedule": {"dates": ["2028-02-29"]}})[0]
        self.assertEqual(config["schedule"]["dates"], ["2028-02-29"])
        self.assertIsNone(config["schedule"]["weekdays"])
        self.assertEqual(config["schedule"]["time"], "08:30")
        self.assertTrue(config["schedule"]["catch_up"])

    def test_original_daily_and_weekly_defaults_unchanged(self):
        self.assertEqual(self.load({})[0]["schedule"]["weekdays"], list(range(7)))
        self.assertIsNone(self.load({})[0]["schedule"]["dates"])
        self.assertEqual(self.load({"schedule": {"weekdays": [0, 2]}})[0]["schedule"]["weekdays"], [0, 2])

    def test_invalid_dates_are_rejected(self):
        invalid = [[], "2027-03-15", True, [True], [None], [{}], ["2027-02-29"],
                   ["2027-13-01"], ["0000-01-01"], ["20270315"], ["2027-3-15"],
                   ["2027-W11-1"], ["2027-03-15T08:30:00"], ["2027-03-15 "],
                   ["2027-03-15", "2027-03-15"], ["2027-03-15"] * 1001]
        for dates in invalid:
            with self.subTest(dates=dates), self.assertRaises(ValueError):
                self.load({"schedule": {"dates": dates}})

    def test_two_selectors_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "either"):
            self.load({"schedule": {"weekdays": [0], "dates": ["2027-03-15"]}})

    def test_explicit_null_disables_only_the_other_selector(self):
        self.assertEqual(self.load({"schedule": {"weekdays": None, "dates": ["2027-03-15"]}})[0]["schedule"]["dates"], ["2027-03-15"])
        self.assertEqual(self.load({"schedule": {"weekdays": [0], "dates": None}})[0]["schedule"]["weekdays"], [0])
        with self.assertRaises(ValueError):
            self.load({"schedule": {"weekdays": None, "dates": None}})

    def test_profile_dates_override_inherited_weekdays(self):
        configs = self.load({"schedule": {"weekdays": [0], "time": "09:00"}, "profiles": [
            {"id": "one-off", "schedule": {"dates": ["2027-03-17"]}},
            {"id": "weekly"},
        ]})
        self.assertIsNone(configs[0]["schedule"]["weekdays"])
        self.assertEqual(configs[1]["schedule"]["weekdays"], [0])
        self.assertEqual(configs[0]["schedule"]["time"], "09:00")

    def test_profile_weekdays_override_inherited_dates(self):
        configs = self.load({"schedule": {"dates": ["2027-03-17"]}, "profiles": [
            {"id": "weekly", "schedule": {"weekdays": [2]}},
            {"id": "one-off", "schedule": {"time": "10:00"}},
        ]})
        self.assertIsNone(configs[0]["schedule"]["dates"])
        self.assertEqual(configs[0]["schedule"]["weekdays"], [2])
        self.assertIsNone(configs[1]["schedule"]["weekdays"])
        self.assertEqual(configs[1]["schedule"]["dates"], ["2027-03-17"])
        self.assertEqual(configs[1]["schedule"]["time"], "10:00")

    def test_validate_expired_calendar_succeeds_offline(self):
        self.load({"schedule": {"dates": ["2000-01-01"]}})
        output = io.StringIO()
        with patch("literature_digest.http.HttpClient.request", side_effect=AssertionError("No network")), redirect_stdout(output):
            self.assertEqual(main(["--config", str(self.path), "validate"]), 0)
        result = json.loads(output.getvalue())[0]
        self.assertEqual(result["status"], "valid")
        self.assertIsNone(result["next_run"])
        self.assertFalse(result["schedule_installed"])


class CalendarInstants(unittest.TestCase):
    def config(self, dates, zone="UTC", at="08:30", catch_up=True):
        config = copy.deepcopy(DEFAULTS)
        config["timezone"] = zone
        config["schedule"] = {"dates": dates, "weekdays": None, "time": at, "catch_up": catch_up}
        return config

    def test_dates_only_never_recur_daily_weekly_or_annually(self):
        config = self.config(["2026-10-05"])
        self.assertFalse(is_due(config, utc(2026, 10, 5, 8, 29)))
        self.assertTrue(is_due(config, utc(2026, 10, 5, 8, 30)))
        for now in (utc(2026, 10, 6, 9), utc(2026, 10, 12, 9), utc(2027, 10, 5, 9)):
            with self.subTest(now=now):
                self.assertFalse(is_due(config, now))
                self.assertIsNone(next_run(config, now))

    def test_missed_dates_do_not_replay(self):
        config = self.config(["2026-10-03", "2026-10-05"])
        now = utc(2026, 10, 4, 23)
        self.assertFalse(is_due(config, now))
        self.assertEqual(next_run(config, now), "2026-10-05T08:30:00+00:00")

    def test_calendar_is_sorted_and_searches_beyond_fortnight(self):
        config = self.config(["2028-03-15", "2027-03-15", "2025-03-15"])
        self.assertEqual(next_run(config, utc(2026, 10, 3)), "2027-03-15T08:30:00+00:00")
        self.assertEqual(next_run(config, utc(2027, 3, 16)), "2028-03-15T08:30:00+00:00")

    def test_date_is_profile_local_not_utc(self):
        config = self.config(["2026-10-05"], "Asia/Shanghai", "00:30")
        self.assertFalse(is_due(config, utc(2026, 10, 4, 16, 29)))
        self.assertTrue(is_due(config, utc(2026, 10, 4, 16, 30)))
        self.assertFalse(is_due(config, utc(2026, 10, 5, 16, 30)))

    def test_same_day_catchup_even_without_future_instant(self):
        config = self.config(["2026-10-05"])
        self.assertTrue(is_due(config, utc(2026, 10, 5, 23, 59)))
        self.assertIsNone(next_run(config, utc(2026, 10, 5, 23, 59)))

    def test_no_catchup_only_scheduled_minute(self):
        config = self.config(["2026-10-05"], catch_up=False)
        self.assertTrue(is_due(config, utc(2026, 10, 5, 8, 30, 59)))
        self.assertFalse(is_due(config, utc(2026, 10, 5, 8, 31)))

    def test_spring_gap_same_day_first_valid_minute(self):
        config = self.config(["2026-03-08"], "America/New_York", "02:30")
        self.assertEqual(next_run(config, utc(2026, 3, 8, 6, 55)), "2026-03-08T03:00:00-04:00")
        self.assertTrue(is_due(config, utc(2026, 3, 8, 7)))
        self.assertFalse(is_due(config, utc(2026, 3, 9, 7)))

    def test_spring_gap_no_catchup_does_not_move_date(self):
        config = self.config(["2026-03-08"], "America/New_York", "02:30", False)
        self.assertFalse(is_due(config, utc(2026, 3, 8, 7)))
        self.assertIsNone(next_run(config, utc(2026, 3, 8, 6)))

    def test_autumn_fold_uses_first_instant_once(self):
        config = self.config(["2026-11-01"], "America/New_York", "01:30")
        self.assertEqual(next_run(config, utc(2026, 11, 1, 5)), "2026-11-01T01:30:00-04:00")
        self.assertIsNone(next_run(config, utc(2026, 11, 1, 6, 15)))
        self.assertTrue(is_due(config, utc(2026, 11, 1, 6, 30)))
        config["schedule"]["catch_up"] = False
        self.assertFalse(is_due(config, utc(2026, 11, 1, 6, 30)))

    def test_whole_day_timezone_skip_does_not_shift_to_another_date(self):
        config = self.config(["2011-12-30"], "Pacific/Apia", "08:30")
        self.assertIsNone(next_run(config, utc(2011, 12, 29)))
        self.assertFalse(is_due(config, utc(2011, 12, 30, 19)))

    def test_tick_exhausted_calendar_is_not_an_error_or_retrieval(self):
        config = self.config(["2026-10-05"])
        with patch("literature_digest.cli.run", side_effect=AssertionError("No run")):
            result = _run_one(config, "tick", True, utc(2026, 10, 6, 9))
        self.assertEqual(result["status"], "not_due")
        self.assertIsNone(result["next_run"])

    def test_immediate_run_intentionally_bypasses_calendar(self):
        config = self.config(["2026-10-05"])
        with patch("literature_digest.cli.run", return_value={"status": "dry_run"}) as execute:
            result = _run_one(config, "run", False, utc(2026, 10, 6, 9))
        execute.assert_called_once()
        self.assertEqual(result["status"], "dry_run")


class TopicCalendarDelivery(unittest.TestCase):
    def test_shared_mailbox_independent_topics_days_and_idempotency(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            profiles = []
            for identifier, topic, schedule in (
                ("monday-bvocs", "BVOCs", {"weekdays": [0]}),
                ("wednesday-trees", "Tree species", {"weekdays": [2]}),
                ("dated-urban-forest", "Urban forest", {"dates": ["2026-10-05"]}),
            ):
                profiles.append({"id": identifier, "recipient": "reader@example.org", "schedule": schedule,
                                 "topics": [{"id": identifier, "name": topic, "queries": [topic]}]})
            path.write_text(json.dumps({"timezone": "UTC", "sources": ["crossref"], "profiles": profiles}))
            configs = load_configs(str(path))
            install_model_double(self, configs[0])
            for config in configs[1:]:
                config["llm"]["enabled"] = True
            deliveries, retrievals = [], []

            def fetch(http, config, *args):
                retrievals.append(config["profile_id"])
                return ([Paper(title=config["topics"][0]["name"], source="crossref", source_id=config["profile_id"],
                               doi="10.9999/" + config["profile_id"], url="https://example.org/synthetic", abstract="Synthetic metadata.",
                               provenance=[{"date_fields": {"published-online": {"date-parts": [[2026, 10, 3]]}}}])], {"complete": True})

            def send(payload, config, state, identifier):
                deliveries.append((config["profile_id"], payload["recipient"], identifier))
                state.mark_sent(identifier)

            def execute(config, **kwargs):
                return run(config, **kwargs, fetchers={"crossref": fetch}, mail_adapter=send)

            with patch("literature_digest.cli.run", side_effect=execute):
                monday = _many(configs, "tick", True, utc(2026, 10, 5, 9))
                repeated = _many(configs, "tick", True, utc(2026, 10, 5, 10))
                tuesday = _many(configs, "tick", True, utc(2026, 10, 6, 9))
                wednesday = _many(configs, "tick", True, utc(2026, 10, 7, 9))
                next_monday = _many(configs, "tick", True, utc(2026, 10, 12, 9))
            self.assertEqual([r["status"] for r in monday], ["sent", "not_due", "sent"])
            self.assertEqual([r["status"] for r in repeated], ["already_sent", "not_due", "already_sent"])
            self.assertEqual([r["status"] for r in tuesday], ["not_due"] * 3)
            self.assertEqual([r["status"] for r in wednesday], ["not_due", "sent", "not_due"])
            self.assertEqual([r["status"] for r in next_monday], ["sent", "not_due", "not_due"])
            self.assertEqual([entry[0] for entry in deliveries], ["monday-bvocs", "dated-urban-forest", "wednesday-trees", "monday-bvocs"])
            self.assertEqual(len({entry[2] for entry in deliveries}), 4)
            self.assertEqual(retrievals, [entry[0] for entry in deliveries])
            self.assertTrue(all(entry[1] == "reader@example.org" for entry in deliveries))
            self.assertEqual(monday[0]["paper_count"], 1)
            self.assertEqual(next_monday[0]["paper_count"], 0)

    def test_explicit_date_dst_fold_delivery_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            config = CalendarInstants().config(["2026-11-01"], "America/New_York", "01:30")
            config.update(state_path=str(Path(directory) / "state.db"), output_dir=str(Path(directory) / "output"), sources=["crossref"])
            install_model_double(self, config)
            sent = []

            def send(payload, config, state, identifier):
                sent.append(identifier)
                state.mark_sent(identifier)

            def execute(config, **kwargs):
                return run(config, **kwargs, fetchers={"crossref": lambda *args: ([], {"complete": True})}, mail_adapter=send)

            with patch("literature_digest.cli.run", side_effect=execute):
                first = _run_one(config, "tick", True, utc(2026, 11, 1, 5, 30))
                second = _run_one(config, "tick", True, utc(2026, 11, 1, 6, 30))
            self.assertEqual(first["status"], "sent")
            self.assertEqual(second["status"], "already_sent")
            self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()

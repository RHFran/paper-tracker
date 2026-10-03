"""No network or real keys: model onboarding, multi-profile keys and safe storage."""
from argparse import Namespace
import getpass
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from literature_digest.config import load_configs
from literature_digest.configure_model import configure_model
from literature_digest.environment import read_environment_file


class ModelConfiguration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"
        self.path.write_text(json.dumps({"recipient": "reader@example.org", "timezone": "UTC", "llm": {"enabled": False}, "mail": {"enabled": False}}), encoding="utf-8")
        self.args = Namespace(config=str(self.path), profile=None, secrets_file=None, replace=False)
        self.log = io.StringIO()

    def configure(self, answers=None, key="fake-local-test-key"):
        answers = iter(answers or ["deepseek", "", "test-model", "", "yes"])
        with patch("literature_digest.http.HttpClient.request", side_effect=AssertionError("No network")):
            return configure_model(self.args, input_fn=lambda prompt: next(answers), secret_fn=lambda prompt: key, output_fn=lambda text: print(text, file=self.log))

    def test_hidden_key_saved_only_in_secret_file_and_redacted_report(self):
        result = self.configure(key="fake-'quoted'-$(literal)-test-key")
        self.assertEqual(result["status"], "model_configured")
        self.assertFalse(result["network_used"])
        secret = Path(self.temp.name) / ".env"
        self.assertEqual(read_environment_file(secret)["PAPER_TRACKER_DEFAULT_API_KEY"], "fake-'quoted'-$(literal)-test-key")
        configs = load_configs(str(self.path))
        self.assertTrue(configs[0]["llm"]["enabled"])
        self.assertFalse(configs[0]["mail"]["enabled"])
        for output in (self.log.getvalue(), json.dumps(result), self.path.read_text(encoding="utf-8")):
            self.assertNotIn("fake-'quoted'-$(literal)-test-key", output)
        if os.name != "nt":
            self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_cancel_preserves_config_and_creates_no_secret(self):
        original = self.path.read_bytes()
        result = self.configure(["openai", "", "custom-model", "", "no"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.path.parent / ".env").exists())

    def test_existing_model_and_slot_not_overwritten_without_replace(self):
        self.configure()
        original = self.path.read_bytes(), (self.path.parent / ".env").read_bytes()
        with self.assertRaisesRegex(ValueError, "already has"):
            self.configure()
        self.assertEqual(original, (self.path.read_bytes(), (self.path.parent / ".env").read_bytes()))
        self.args.replace = True
        self.configure(key="replacement-fake-key")
        self.assertEqual(read_environment_file(self.path.parent / ".env")["PAPER_TRACKER_DEFAULT_API_KEY"], "replacement-fake-key")

    def test_preserves_unrelated_secrets_and_slot(self):
        env = self.path.parent / ".env"
        env.write_text("# Keep this operator note\nLITERATURE_SMTP_PASSWORD='fake-mail-value'\n", encoding="utf-8")
        self.configure()
        self.assertIn("# Keep this operator note", env.read_text(encoding="utf-8"))
        self.assertEqual(read_environment_file(env)["LITERATURE_SMTP_PASSWORD"], "fake-mail-value")

    def test_profiles_select_independent_models_and_credentials(self):
        self.path.write_text(json.dumps({"timezone": "UTC", "profiles": [{"id": "forest-weekly", "recipient": "reader@example.org"}, {"id": "battery-daily", "recipient": "reader@example.org"}]}))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.configure()
        self.args.profile = "forest-weekly"
        self.configure(key="fake-forest-key")
        self.args.profile = "battery-daily"
        self.configure(["qwen", "", "qwen-example", "", "yes"], key="fake-battery-key")
        configs = load_configs(str(self.path))
        self.assertEqual(configs[0]["llm"]["api_key_env"], "PAPER_TRACKER_FOREST_WEEKLY_API_KEY")
        self.assertEqual(configs[1]["llm"]["api_key_env"], "PAPER_TRACKER_BATTERY_DAILY_API_KEY")
        self.assertEqual(len(read_environment_file(self.path.parent / ".env")), 6)
        self.args.replace = True
        with self.assertRaisesRegex(ValueError, "another subscription"):
            self.configure(["qwen", "", "qwen-example", "forest_weekly", "yes"])

    def test_rejects_key_newline_and_unicode_line_separators(self):
        original = self.path.read_bytes()
        for key in ("fake\nOTHER=value", "fake\rOTHER=value", "fake\x00value", "fake\u2028OTHER=value"):
            with self.subTest(key=repr(key)), self.assertRaisesRegex(ValueError, "single-line"):
                self.configure(key=key)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.path.parent / ".env").exists())

    def test_rejects_unsafe_endpoint_and_public_secret_filename(self):
        for url in ("http://example.org/v1", "https://user:key@example.org/v1", "https://example.org/v1?key=secret", "https://example.org/v1/chat/completions"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "HTTPS base URL"):
                self.configure(["custom", url])
        self.args.secrets_file = ".env.example"
        with self.assertRaisesRegex(ValueError, "Secrets filename"):
            self.configure()

    def test_getpass_refuses_echo_fallback(self):
        answers = iter(["deepseek", "", "test-model", ""])
        def fail(prompt):
            import warnings
            warnings.warn("no terminal", getpass.GetPassWarning)
        with self.assertRaisesRegex(ValueError, "Secure terminal"):
            configure_model(self.args, input_fn=lambda prompt: next(answers), secret_fn=fail, output_fn=lambda text: None)
        self.assertFalse((self.path.parent / ".env").exists())

    def test_direct_cli_loads_private_environment_and_restores_it(self):
        from contextlib import redirect_stdout
        from literature_digest.cli import main
        self.configure()
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
            self.assertEqual(main(["--env-file", str(self.path.parent / ".env"), "--config", str(self.path), "validate"]), 0)
            self.assertNotIn("PAPER_TRACKER_DEFAULT_API_KEY", os.environ)
        result = json.loads(output.getvalue())
        self.assertTrue(result[0]["live_ready"])
        self.assertNotIn("fake-local-test-key", output.getvalue())

    def test_environment_parser_rejects_duplicate_and_malformed_lines(self):
        path = self.path.parent / ".env"
        for text in ("KEY=one\nKEY=two\n", "not-a-value\n", "KEY='unclosed\n", "BAD NAME=value\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                path.write_text(text, encoding="utf-8")
                read_environment_file(path)


if __name__ == "__main__":
    unittest.main()

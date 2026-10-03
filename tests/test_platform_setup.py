"""Offline setup/launcher and lock contracts, including real process contention."""
import errno
import importlib.util
import io
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from literature_digest.locking import exclusive_file_lock, _windows_lock

ROOT = Path(__file__).resolve().parent.parent


def lock_probe(path, connection):
    try:
        with exclusive_file_lock(path):
            connection.send("acquired")
    except RuntimeError:
        connection.send("blocked")
    finally:
        connection.close()


class CrossPlatformLock(unittest.TestCase):
    def test_process_contention_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "ledger.lock")
            context = multiprocessing.get_context("spawn")
            def probe():
                receive, send = context.Pipe(duplex=False)
                process = context.Process(target=lock_probe, args=(path, send))
                process.start()
                send.close()
                try:
                    self.assertTrue(receive.poll(20), "lock probe did not finish")
                    result = receive.recv()
                    process.join(20)
                    self.assertEqual(process.exitcode, 0)
                    return result
                finally:
                    receive.close()
                    if process.is_alive():
                        process.terminate()
                        process.join(10)
            with exclusive_file_lock(path):
                self.assertEqual(probe(), "blocked")
            self.assertEqual(probe(), "acquired")
            self.assertTrue(Path(path).exists(), "lock file must not be unlinked")

    def test_exception_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "ledger.lock")
            with self.assertRaises(ValueError):
                with exclusive_file_lock(path):
                    raise ValueError("body")
            with exclusive_file_lock(path):
                pass

    def test_windows_byte_offset_and_unlock(self):
        events = []
        with tempfile.TemporaryFile("w+b") as handle:
            module = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2)
            module.locking = lambda fd, mode, size: events.append((fd, mode, size, handle.tell()))
            with patch.dict(sys.modules, {"msvcrt": module}):
                release = _windows_lock(handle)
                handle.seek(7)
                release()
            self.assertEqual([(e[1], e[2], e[3]) for e in events], [(1, 1, 0), (2, 1, 0)])
            handle.seek(0)
            self.assertEqual(handle.read(), b"\0")

    def test_windows_contention_reports_busy_but_other_errors_propagate(self):
        with tempfile.TemporaryFile("w+b") as handle:
            for number, expected in ((errno.EACCES, RuntimeError), (errno.EBADF, OSError)):
                def fail(*args):
                    raise OSError(number, "test error")
                module = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=fail)
                with self.subTest(errno=number), patch.dict(sys.modules, {"msvcrt": module}), self.assertRaises(expected):
                    _windows_lock(handle)


class LauncherSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("paper_tracker_launcher", ROOT / "scripts/launch.py")
        cls.launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.launcher)

    def setUp(self):
        self.previous = Path.cwd()
        self.addCleanup(os.chdir, self.previous)
        self.configs = [{"profile_id": "default", "llm": {"enabled": True, "api_key_env": "PAPER_TRACKER_TEST_KEY"}, "mail": {"enabled": True, "password_env": "PAPER_TRACKER_TEST_SMTP"}}]

    def test_default_launch_help_and_no_auto_send(self):
        with patch("literature_digest.cli.main", return_value=0) as run:
            self.assertEqual(self.launcher.main([]), 0)
            run.assert_called_once_with(["--help"])
        with patch("literature_digest.cli.main", return_value=0) as run:
            self.launcher.main(["--config", "my file.json", "run"])
            run.assert_called_once_with(["--config", "my file.json", "run"])

    def test_hidden_values_process_only_and_no_smtp_prompt_for_dry_run(self):
        output = io.StringIO()
        def run(args):
            self.assertEqual(os.environ.get("PAPER_TRACKER_TEST_KEY"), "fake-unit-test-value")
            self.assertNotIn("PAPER_TRACKER_TEST_SMTP", os.environ)
            self.assertNotIn("--send", args)
            return 0
        with patch.dict(os.environ, {}, clear=True), patch("literature_digest.config.load_configs", return_value=self.configs), patch.object(sys.stdin, "isatty", return_value=True), patch("getpass.getpass", return_value="fake-unit-test-value") as prompt, patch("literature_digest.cli.main", side_effect=run), redirect_stderr(output):
            self.assertEqual(self.launcher.main(["--prompt-secrets", "run"]), 0)
            self.assertNotIn("PAPER_TRACKER_TEST_KEY", os.environ)
            prompt.assert_called_once_with("PAPER_TRACKER_TEST_KEY: ")
        self.assertNotIn("fake-unit-test-value", output.getvalue())

    def test_unattended_missing_secrets_refuses_before_launch(self):
        with patch.dict(os.environ, {}, clear=True), patch("literature_digest.config.load_configs", return_value=self.configs), patch.object(sys.stdin, "isatty", return_value=False), patch("literature_digest.cli.main") as run, patch("getpass.getpass") as prompt, redirect_stderr(io.StringIO()):
            self.assertEqual(self.launcher.main(["--prompt-secrets", "run", "--send"]), 1)
            run.assert_not_called()
            prompt.assert_not_called()

    def test_preview_does_not_request_credentials(self):
        with patch("literature_digest.config.load_configs", return_value=self.configs), patch("getpass.getpass") as prompt, patch("literature_digest.cli.main", return_value=0) as run:
            self.assertEqual(self.launcher.main(["--prompt-secrets", "preview"]), 0)
            prompt.assert_not_called()
            run.assert_called_once_with(["preview"])

    def test_env_file_is_literal_and_existing_environment_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.env"
            path.write_text("# Private data, not shell code\nPAPER_TRACKER_TEST_KEY='$(never-execute-this)'\nPAPER_TRACKER_TEST_SMTP=file-value\n", encoding="utf-8")
            def run(args):
                self.assertEqual(os.environ["PAPER_TRACKER_TEST_KEY"], "$(never-execute-this)")
                self.assertEqual(os.environ["PAPER_TRACKER_TEST_SMTP"], "existing")
                self.assertEqual(args, ["validate"])
                return 0
            with patch.dict(os.environ, {"PAPER_TRACKER_TEST_SMTP": "existing"}, clear=True), patch("literature_digest.config.load_configs", return_value=self.configs), patch("literature_digest.cli.main", side_effect=run):
                self.assertEqual(self.launcher.main(["--env-file", str(path), "validate"]), 0)
                self.assertNotIn("PAPER_TRACKER_TEST_KEY", os.environ)
                self.assertEqual(os.environ["PAPER_TRACKER_TEST_SMTP"], "existing")

    def test_env_file_ignores_unconfigured_variables_without_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.env"
            path.write_text("PATH=secret-sentinel\n", encoding="utf-8")
            output = io.StringIO()
            original = os.environ.get("PATH")
            def check(args):
                self.assertEqual(os.environ.get("PATH"), original)
                return 0
            with patch("literature_digest.config.load_configs", return_value=self.configs), patch("literature_digest.cli.main", side_effect=check), redirect_stderr(output):
                self.assertEqual(self.launcher.main(["--env-file", str(path), "validate"]), 0)
                self.assertNotIn("secret-sentinel", output.getvalue())

    def test_setup_help_no_mutation(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/setup.py"), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Never send or install a scheduler", result.stdout)


if __name__ == "__main__":
    unittest.main()

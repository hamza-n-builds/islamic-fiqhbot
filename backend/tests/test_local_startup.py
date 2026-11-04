"""Startup regressions. No model/provider calls or package downloads."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("bootstrap_local", Path(__file__).parents[1] / "bootstrap_local.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fiqhbot startup ")
        self.addCleanup(self.temp.cleanup)
        self.backend = Path(self.temp.name)
        self.enterContext(patch.object(bootstrap, "BACKEND_DIR", self.backend))
        self.nltk = self.enterContext(patch.object(bootstrap, "prepare_nltk"))
        self.environment = self.backend / "venv"
        self.python = self.environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        (self.backend / "requirements.txt").write_text("flask>=3.0\n", encoding="utf-8")

    def mark_ready(self):
        self.environment.mkdir(exist_ok=True)
        digest = hashlib.sha256((self.backend / "requirements.txt").read_bytes()).hexdigest()
        (self.environment / ".fiqhbot-requirements.sha256").write_text(digest + "\n", encoding="ascii")

    def test_python_probe_checks_version_bits_prefix_and_return_code(self):
        for version, bits, prefix, code, expected in (
            ([3, 11], 64, self.environment, 0, True),
            ([3, 15], 64, self.environment, 0, False),
            ([3, 11], 32, self.environment, 0, False),
            ([3, 11], 64, self.backend, 0, False),
            ([3, 11], 64, self.environment, 1, False),
        ):
            result = Mock(returncode=code, stdout=json.dumps({"version": version, "bits": bits, "prefix": str(prefix)}))
            with self.subTest(version=version, bits=bits, code=code, prefix=prefix), patch.object(bootstrap.subprocess, "run", return_value=result):
                self.assertEqual(bootstrap.python_is_usable(self.python, expected_prefix=self.environment), expected)

    def test_broken_missing_or_hung_python_is_rejected(self):
        for failure in (FileNotFoundError(), subprocess.TimeoutExpired("python", 10)):
            with self.subTest(failure=type(failure).__name__), patch.object(bootstrap.subprocess, "run", side_effect=failure):
                self.assertFalse(bootstrap.python_is_usable(self.python))
        with patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=1, stdout="")):
            self.assertFalse(bootstrap.python_is_usable(self.python))

    def test_broken_environment_is_preserved_not_deleted(self):
        self.environment.mkdir()
        (self.environment / "sentinel.txt").write_text("existing packages", encoding="utf-8")
        with patch.object(bootstrap, "BACKEND_DIR", self.backend):
            backup = bootstrap.preserve_broken_environment(self.environment)
        self.assertEqual((backup / "sentinel.txt").read_text(), "existing packages")
        self.assertFalse(self.environment.exists())
        self.assertEqual(backup.parent, self.backend)

    def test_environment_backup_refuses_other_paths(self):
        with patch.object(bootstrap, "BACKEND_DIR", self.backend):
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.preserve_broken_environment(self.backend / "other")

    def test_environment_backup_refuses_links(self):
        with patch.object(bootstrap, "BACKEND_DIR", self.backend), patch.object(Path, "lstat", return_value=Mock(st_file_attributes=0)), patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(bootstrap.SetupError, "is a link"):
                bootstrap.preserve_broken_environment(self.environment)

    def test_check_only_never_rebuilds_broken_environment(self):
        with patch.object(bootstrap, "python_is_usable", return_value=False), patch.object(bootstrap, "run_checked") as run, patch.object(bootstrap, "preserve_broken_environment") as preserve:
            with self.assertRaisesRegex(bootstrap.SetupError, "setup-only"):
                bootstrap.prepare_environment(self.backend, check_only=True)
            run.assert_not_called()
            preserve.assert_not_called()
        self.assertEqual(sorted(p.name for p in self.backend.iterdir()), ["requirements.txt"])

    def test_check_only_checks_imports_without_installing_or_writing_marker(self):
        self.environment.mkdir()
        with patch.object(bootstrap, "python_is_usable", return_value=True), patch.object(bootstrap, "check_dependencies") as check, patch.object(bootstrap, "run_checked") as run:
            self.assertEqual(bootstrap.prepare_environment(self.backend, check_only=True), self.python)
            check.assert_called_once_with(self.python, self.backend, imports=True)
            self.nltk.assert_called_once_with(self.python, self.backend, check_only=True)
            run.assert_not_called()
        self.assertFalse((self.environment / ".fiqhbot-requirements.sha256").exists())

    def test_repeated_start_reuses_healthy_environment_without_install(self):
        self.mark_ready()
        with patch.object(bootstrap, "python_is_usable", return_value=True), patch.object(bootstrap, "check_dependencies") as check, patch.object(bootstrap, "run_checked") as run:
            self.assertEqual(bootstrap.prepare_environment(self.backend), self.python)
            check.assert_called_once_with(self.python, self.backend)
            run.assert_not_called()

    def test_changed_requirements_install_and_mark_only_after_checks(self):
        self.mark_ready()
        (self.backend / "requirements.txt").write_text("flask>=3.1\n", encoding="utf-8")
        with patch.object(bootstrap, "python_is_usable", return_value=True), patch.object(bootstrap, "check_dependencies") as check, patch.object(bootstrap, "run_checked") as run:
            bootstrap.prepare_environment(self.backend)
            self.assertEqual(run.call_count, 2)
            self.assertIn("ensurepip", run.call_args_list[0].args[0])
            self.assertIn("install", run.call_args_list[1].args[0])
            check.assert_called_once_with(self.python, self.backend, imports=True)
        self.assertEqual((self.environment / ".fiqhbot-requirements.sha256").read_text().strip(), hashlib.sha256((self.backend / "requirements.txt").read_bytes()).hexdigest())

    def test_failed_install_is_retryable_and_never_marks_ready(self):
        self.environment.mkdir()
        with patch.object(bootstrap, "python_is_usable", return_value=True), patch.object(bootstrap, "run_checked", side_effect=bootstrap.SetupError("installation failed")):
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.prepare_environment(self.backend)
        self.assertFalse((self.environment / ".fiqhbot-requirements.sha256").exists())

    def test_failed_nltk_setup_never_marks_environment_ready(self):
        self.environment.mkdir()
        self.nltk.side_effect = bootstrap.SetupError("missing tokenizer data")
        with patch.object(bootstrap, "python_is_usable", return_value=True), patch.object(bootstrap, "run_checked"), patch.object(bootstrap, "check_dependencies"):
            with self.assertRaisesRegex(bootstrap.SetupError, "tokenizer"):
                bootstrap.prepare_environment(self.backend)
        self.assertFalse((self.environment / ".fiqhbot-requirements.sha256").exists())

    def test_missing_dependency_retriggers_setup(self):
        self.mark_ready()
        with patch.object(bootstrap, "python_is_usable", return_value=True), patch.object(bootstrap, "check_dependencies", side_effect=[bootstrap.SetupError("missing"), None]), patch.object(bootstrap, "run_checked") as run:
            bootstrap.prepare_environment(self.backend)
            self.assertEqual(run.call_count, 2)

    def test_fresh_setup_creates_environment_and_checks_it_before_install(self):
        def fake_run(command, **kwargs):
            if "venv" in command:
                self.environment.mkdir()
        with patch.object(bootstrap, "python_is_usable", side_effect=[False, True]), patch.object(bootstrap, "run_checked", side_effect=fake_run) as run, patch.object(bootstrap, "check_dependencies"):
            bootstrap.prepare_environment(self.backend)
            self.assertIn("venv", run.call_args_list[0].args[0])
            self.assertTrue((self.environment / ".fiqhbot-requirements.sha256").exists())

    def test_child_process_failure_and_timeout_fail_closed(self):
        with patch.object(bootstrap.subprocess, "run", return_value=Mock(returncode=1)):
            with self.assertRaises(bootstrap.SetupError):
                bootstrap.run_checked(["python"], cwd=self.backend)
        with patch.object(bootstrap.subprocess, "run", side_effect=subprocess.TimeoutExpired("python", 1)):
            with self.assertRaisesRegex(bootstrap.SetupError, "timed out"):
                bootstrap.run_checked(["python"], cwd=self.backend, timeout=1)

    def test_read_only_dependency_check_validates_requirements_without_network(self):
        with patch.object(bootstrap, "run_checked") as run:
            bootstrap.check_dependencies(self.python, self.backend, imports=True)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn("check", commands[1])
            for flag in ("--dry-run", "--no-index", "--no-deps", "--no-cache-dir", "--isolated"):
                self.assertIn(flag, commands[2])
            self.assertIn(bootstrap.IMPORT_PROBE, commands[3])

    def test_setup_and_check_modes_never_start_app(self):
        with patch.object(bootstrap, "prepare_environment", return_value=self.python), patch.object(bootstrap.subprocess, "call") as launch:
            self.assertEqual(bootstrap.main(["--setup-only"]), 0)
            self.assertEqual(bootstrap.main(["--check"]), 0)
            launch.assert_not_called()

    def test_normal_launch_forwards_no_browser_and_exit_status(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "synthetic-test-key"}), patch.object(bootstrap, "prepare_environment", return_value=self.python), patch.object(bootstrap.subprocess, "call", return_value=7) as launch:
            self.assertEqual(bootstrap.main(["--no-browser"]), 7)
            self.assertIn("--no-browser", launch.call_args.args[0])
            self.assertEqual(launch.call_args.kwargs["cwd"], bootstrap.BACKEND_DIR)

    def test_failed_setup_never_starts_app(self):
        with patch.object(bootstrap, "prepare_environment", side_effect=bootstrap.SetupError("test failure")), patch.object(bootstrap.subprocess, "call") as launch:
            self.assertEqual(bootstrap.main(["--setup-only"]), 1)
            launch.assert_not_called()

    def test_wrong_bootstrap_python_is_rejected(self):
        with patch.object(sys, "version_info", (3, 15)), patch.object(bootstrap, "prepare_environment") as prepare:
            self.assertEqual(bootstrap.main(["--setup-only"]), 1)
            prepare.assert_not_called()

    def test_parallel_setup_is_refused_and_lock_is_released(self):
        with bootstrap.setup_lock(self.backend):
            with self.assertRaisesRegex(bootstrap.SetupError, "Another FIQHBOT launcher"):
                with bootstrap.setup_lock(self.backend):
                    self.fail("Two installers acquired the lock")
        with bootstrap.setup_lock(self.backend):
            pass

    @unittest.skipUnless(os.name == "nt", "Windows launcher")
    def test_windows_launcher_quotes_paths_forwards_arguments_and_keeps_exit_code(self):
        launcher = self.backend / "start_fiqhbot.cmd"
        shutil.copyfile(Path(__file__).parents[2] / "start_fiqhbot.cmd", launcher)
        stub = self.backend / "backend" / "bootstrap_local.py"
        stub.parent.mkdir()
        stub.write_text("import json,sys; print(json.dumps(sys.argv[1:])); sys.exit(7)\n", encoding="utf-8")
        env = dict(os.environ, FIQHBOT_PYTHON=sys.executable, FIQHBOT_NO_PAUSE="1")
        result = subprocess.run(["cmd.exe", "/d", "/c", str(launcher), "--no-browser"],
                                cwd=self.backend.parent, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout.strip()), ["--no-browser"])

    @unittest.skipUnless(os.name == "nt", "Windows launcher")
    def test_windows_launcher_rejects_invalid_explicit_python_without_starting(self):
        launcher = self.backend / "start_fiqhbot.cmd"
        shutil.copyfile(Path(__file__).parents[2] / "start_fiqhbot.cmd", launcher)
        env = dict(os.environ, FIQHBOT_PYTHON=str(self.backend / "missing python.exe"), FIQHBOT_NO_PAUSE="1")
        result = subprocess.run(["cmd.exe", "/d", "/c", str(launcher), "--check"],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("requires a working Python 3.11", result.stdout)


if __name__ == "__main__":
    unittest.main()

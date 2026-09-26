"""Actual local test execution and Git-bound evidence persistence."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import ctxzip
from ctxzip_core.git_state import capture_git_snapshot
from ctxzip_core.knowledge import Freshness, KnowledgeStore, TestResult, test_freshness
from ctxzip_core.test_runner import run_and_record_test


@unittest.skipUnless(shutil.which("git"), "Git is required for worktree evidence tests")
class TestRunnerTests(unittest.TestCase):
    def make_repository(self, root: Path) -> Path:
        repository = root / "repository"
        repository.mkdir()
        subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "ctxzip-test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "CtxZip Test"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "commit.gpgsign", "false"], check=True)
        hooks = root / "empty-hooks"
        hooks.mkdir()
        subprocess.run(["git", "-C", str(repository), "config", "core.hooksPath", str(hooks)], check=True)
        (repository / "README.md").write_text("sanitized test repository\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-m", "initial"], check=True, capture_output=True)
        return repository

    def test_runs_command_and_records_only_result_with_pre_run_worktree_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.make_repository(root)
            marker = root / "command-ran.txt"
            command = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"]
            store = KnowledgeStore(root / "archive" / "knowledge")
            before = capture_git_snapshot(repository)

            evidence = run_and_record_test(
                command, store=store, repository_dir=repository, scope=("tests", "tests/unit"),
            )

            self.assertTrue(marker.exists())
            self.assertEqual(evidence.result, TestResult.PASSED)
            self.assertEqual(evidence.exit_code, 0)
            self.assertEqual(evidence.scope, ("tests", "tests/unit"))
            self.assertEqual(evidence.head_sha, before.head_sha)
            self.assertEqual(evidence.worktree_fingerprint, before.fingerprint)
            self.assertEqual(evidence.command, f"{Path(sys.executable).name} <arguments omitted>")
            self.assertNotIn(str(marker), evidence.command)
            self.assertEqual(test_freshness(evidence, before), Freshness.CURRENT)

            (repository / "README.md").write_text("changed after test\n", encoding="utf-8")
            after = capture_git_snapshot(repository)
            self.assertEqual(test_freshness(evidence, after), Freshness.STALE)
            self.assertEqual(store.list_test_evidence(), [evidence])

    def test_invalid_scope_is_rejected_before_command_starts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.make_repository(root)
            marker = root / "must-not-run.txt"
            store = KnowledgeStore(root / "archive" / "knowledge")

            with self.assertRaisesRegex(ValueError, "repository-relative"):
                run_and_record_test(
                    [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
                    store=store,
                    repository_dir=repository,
                    scope=("../outside",),
                )

            self.assertFalse(marker.exists())
            self.assertEqual(store.list_test_evidence(), [])

    def test_spawn_failure_is_recorded_without_fabricated_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.make_repository(root)
            store = KnowledgeStore(root / "archive" / "knowledge")

            evidence = run_and_record_test(
                [str(root / "missing-test-executable.exe")],
                store=store,
                repository_dir=repository,
            )

            self.assertEqual(evidence.result, TestResult.ERROR)
            self.assertIsNone(evidence.exit_code)
            self.assertEqual(store.list_test_evidence(), [evidence])

    def test_cli_wrapper_executes_command_and_persists_localized_test_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.make_repository(root)
            archive = root / "archive"
            (archive / "Demo").mkdir(parents=True)
            settings_path = root / "ctxzip.settings.json"
            settings = deepcopy(ctxzip.DEFAULT_SETTINGS)
            settings["arsiv_klasoru"] = str(archive)
            settings_path.write_text(json.dumps(settings), encoding="utf-8")
            marker = root / "cli-command-ran.txt"
            command = [
                sys.executable, str(Path(__file__).resolve().parents[1] / "ctxzip.py"),
                "--settings", str(settings_path), "--language", "tr",
                "test-run", "--project", "Demo", "--scope", "tests", "--",
                sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            ]

            completed = subprocess.run(
                command, cwd=repository, capture_output=True, text=True, encoding="utf-8", check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue(marker.exists())
            self.assertIn("Test sonucu kaydedildi: başarılı", completed.stdout)
            evidence_path = archive / "Demo" / "knowledge" / "test_runs.json"
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["records"][0]["result"], "passed")
            self.assertEqual(payload["records"][0]["scope"], ["tests"])
            self.assertNotIn(str(marker), evidence_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

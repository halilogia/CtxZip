"""Reviewed summary validity baselines are scoped to clean tracked Git state."""
import json
import contextlib
from dataclasses import replace
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import ctxzip
from ctxzip_core.summary_store import is_manually_edited, read_summary_body, write_summary_file
from ctxzip_core.summary_validity import SummaryValidityError, record_summary_validity
from ctxzip_core.git_state import capture_git_snapshot
from ctxzip_core.retrieval import SummaryCandidate, summary_is_possibly_stale
from ctxzip_core import summary_validity


@unittest.skipUnless(shutil.which("git"), "Git is required for validity-baseline tests")
class SummaryValidityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.repository = root / "repository"
        self.repository.mkdir()
        (self.repository / "src").mkdir()
        (self.repository / "src" / "parser.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repository / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
        self.git("init", "-q")
        hooks_dir = root / "empty-hooks"
        hooks_dir.mkdir()
        self.git("config", "core.hooksPath", str(hooks_dir))
        self.git("config", "user.name", "CtxZip Tests")
        self.git("config", "user.email", "tests@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", "src/parser.py", ".gitignore")
        self.git("commit", "-qm", "initial test fixture")

        self.project = root / "archive" / "Demo"
        summary = self.project / "bolumler" / "B0001.md"
        summary.parent.mkdir(parents=True)
        write_summary_file(
            summary,
            {"tur": "bolum", "kaynak": "codex/session"},
            "Parser behavior",
            "Generated summary body.",
        )
        summary.write_text(
            summary.read_text(encoding="utf-8").replace(
                "Generated summary body.", "User-reviewed summary body.",
            ),
            encoding="utf-8",
        )
        self.summary = summary

    def git(self, *arguments):
        return subprocess.run(
            ["git", *arguments], cwd=self.repository, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def test_records_clean_head_and_explicit_tracked_paths_without_changing_body(self):
        original_metadata, original_body = read_summary_body(self.summary)
        self.assertTrue(is_manually_edited(self.summary))

        name, paths, head = record_summary_validity(
            self.project, "B0001.md", ("src/parser.py", "src\\parser.py"), self.repository,
        )

        metadata, body = read_summary_body(self.summary)
        self.assertEqual(name, "B0001.md")
        self.assertEqual(paths, ("src/parser.py",))
        self.assertEqual(json.loads(metadata["validity_paths"]), ["src/parser.py"])
        self.assertEqual(metadata["validity_head_sha"], head)
        self.assertEqual(head, self.git("rev-parse", "HEAD").stdout.decode().strip())
        self.assertEqual(body, original_body)
        self.assertEqual(metadata["govde_hash"], original_metadata["govde_hash"])
        self.assertTrue(is_manually_edited(self.summary))

    def test_dirty_repository_and_unreviewable_paths_leave_summary_unchanged(self):
        original = self.summary.read_bytes()
        (self.repository / "src" / "parser.py").write_text("VALUE = 2\n", encoding="utf-8")
        with self.assertRaises(SummaryValidityError) as captured:
            record_summary_validity(
                self.project, "B0001.md", ("src/parser.py",), self.repository,
            )
        self.assertEqual(captured.exception.code, "dirty_repository")
        self.assertEqual(self.summary.read_bytes(), original)

        self.git("checkout", "--", "src/parser.py")
        ignored = self.repository / "ignored.py"
        ignored.write_text("SECRET = 'synthetic'\n", encoding="utf-8")
        with self.assertRaises(SummaryValidityError) as captured:
            record_summary_validity(
                self.project, "B0001.md", ("ignored.py",), self.repository,
            )
        self.assertEqual(captured.exception.code, "path_unavailable")
        self.assertEqual(self.summary.read_bytes(), original)

    def test_recorded_path_flows_into_changed_path_staleness_check(self):
        _name, _paths, head = record_summary_validity(
            self.project, "B0001.md", ("src/parser.py",), self.repository,
        )
        metadata, body = read_summary_body(self.summary)
        candidate = SummaryCandidate(
            "Parser behavior", body, "bolumler", metadata, 0, "B0001.md", (), False,
        )
        (self.repository / "src" / "parser.py").write_text("VALUE = 2\n", encoding="utf-8")
        snapshot = capture_git_snapshot(self.repository)

        self.assertIn("src/parser.py", snapshot.changed_files)
        self.assertTrue(summary_is_possibly_stale(
            candidate, snapshot.changed_files, head,
        ))

    def test_repository_change_during_baseline_capture_aborts_without_writing(self):
        initial = capture_git_snapshot(self.repository)
        changed = replace(initial, dirty=True, fingerprint="f" * 64)
        original = self.summary.read_bytes()
        with mock.patch.object(
            summary_validity, "capture_git_snapshot", side_effect=(initial, changed),
        ):
            with self.assertRaises(SummaryValidityError) as captured:
                record_summary_validity(
                    self.project, "B0001.md", ("src/parser.py",), self.repository,
                )

        self.assertEqual(captured.exception.code, "dirty_repository")
        self.assertEqual(self.summary.read_bytes(), original)

    def test_localized_cli_command_records_baseline(self):
        settings_path = Path(self.temporary.name) / "settings.json"
        settings_path.write_text(json.dumps({
            "arsiv_klasoru": str(self.project.parent), "language": "en",
        }), encoding="utf-8")
        arguments = [
            "ctxzip.py", "--settings", str(settings_path), "summary-validity",
            "--project", "Demo", "B0001.md", "--validity-path", "src/parser.py",
        ]
        output = io.StringIO()
        with mock.patch.object(sys, "argv", arguments), \
                mock.patch.object(Path, "cwd", return_value=self.repository), \
                contextlib.redirect_stdout(output):
            ctxzip.main()

        self.assertIn("Recorded validity for B0001.md", output.getvalue())
        metadata, _body = read_summary_body(self.summary)
        self.assertEqual(json.loads(metadata["validity_paths"]), ["src/parser.py"])

    def test_volume_summary_accepts_the_same_reviewed_baseline(self):
        volume_dir = self.project / "ciltler"
        volume_dir.mkdir()
        volume = volume_dir / "C001.md"
        write_summary_file(volume, {"tur": "cilt"}, "Project decisions", "Reviewed volume.")

        name, paths, head = record_summary_validity(
            self.project, "C001.md", ("src/parser.py",), self.repository,
        )

        self.assertEqual(name, "C001.md")
        self.assertEqual(paths, ("src/parser.py",))
        metadata, body = read_summary_body(volume)
        self.assertEqual(metadata["validity_head_sha"], head)
        self.assertEqual(body, "Reviewed volume.")

    def test_invalid_summary_name_paths_and_missing_summary_are_rejected(self):
        cases = (
            ("../outside.md", ("src/parser.py",), "invalid_summary"),
            ("B0001.md", ("../outside.py",), "invalid_path"),
            ("B9999.md", ("src/parser.py",), "invalid_summary"),
            ("B0001.md", (), "paths_required"),
        )
        original = self.summary.read_bytes()
        for summary_name, paths, code in cases:
            with self.subTest(summary=summary_name, paths=paths):
                with self.assertRaises(SummaryValidityError) as captured:
                    record_summary_validity(self.project, summary_name, paths, self.repository)
                self.assertEqual(captured.exception.code, code)
                self.assertEqual(self.summary.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

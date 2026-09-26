from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ctxzip_core.git_state import capture_git_snapshot


class GitSnapshotTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git"), "Git is required for snapshot tests")
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name) / "repo"
        self.repo.mkdir()
        subprocess.run(
            ["git", "-c", "init.defaultBranch=main", "init", "-q", str(self.repo)],
            check=True,
        )
        hooks_dir = self.repo / "test-hooks"
        hooks_dir.mkdir()
        self.git("config", "core.hooksPath", str(hooks_dir))
        self.git("config", "user.name", "CtxZip Test")
        self.git("config", "user.email", "ctxzip@example.invalid")
        (self.repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-qm", "initial")

    def tearDown(self):
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True
        )

    def test_clean_snapshot_records_head_branch_and_stable_fingerprint(self):
        first = capture_git_snapshot(self.repo)
        repeated = capture_git_snapshot(self.repo)

        self.assertTrue(first.is_repository)
        self.assertEqual(first.branch, "main")
        self.assertEqual(len(first.head_sha), 40)
        self.assertFalse(first.dirty)
        self.assertEqual(first.changed_files, ())
        self.assertEqual(first.fingerprint, repeated.fingerprint)

    def test_staged_unstaged_and_untracked_changes_affect_state(self):
        clean = capture_git_snapshot(self.repo)
        (self.repo / "tracked.txt").write_text("staged\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        staged = capture_git_snapshot(self.repo)
        (self.repo / "tracked.txt").write_text("unstaged\n", encoding="utf-8")
        (self.repo / "new.txt").write_text("private content\n", encoding="utf-8")
        untracked = capture_git_snapshot(self.repo)

        self.assertTrue(staged.dirty)
        self.assertNotEqual(clean.staged_diff_hash, staged.staged_diff_hash)
        self.assertEqual(staged.unstaged_diff_hash, clean.unstaged_diff_hash)
        self.assertTrue(untracked.dirty)
        self.assertNotEqual(staged.fingerprint, untracked.fingerprint)
        self.assertNotEqual(staged.unstaged_diff_hash, untracked.unstaged_diff_hash)
        self.assertIn("new.txt", untracked.untracked_files)
        self.assertIn("tracked.txt", untracked.changed_files)
        self.assertIn("new.txt", untracked.changed_files)
        self.assertNotIn("private content", repr(untracked))

    def test_untracked_content_changes_fingerprint_even_when_path_is_unchanged(self):
        path = self.repo / "new.txt"
        path.write_text("first\n", encoding="utf-8")
        first = capture_git_snapshot(self.repo)
        path.write_text("second\n", encoding="utf-8")
        second = capture_git_snapshot(self.repo)

        self.assertEqual(first.untracked_files, second.untracked_files)
        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_non_repository_returns_explicit_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = capture_git_snapshot(Path(tmp))

        self.assertFalse(snapshot.is_repository)
        self.assertIsNone(snapshot.fingerprint)
        self.assertIsNone(snapshot.head_sha)
        self.assertFalse(snapshot.dirty)


if __name__ == "__main__":
    unittest.main()

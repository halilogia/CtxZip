"""Antigravity artifact synchronization preserves prior versions before cleanup."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ctxzip_core.artifacts import sync_markdown_tree


class ArtifactSyncTests(unittest.TestCase):
    def test_updates_additions_and_deletions_reconcile_with_deduplicated_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "archive" / "raw" / "antigravity" / "session"
            history = root / "archive" / "raw" / "antigravity-history" / "session"
            (source / "nested").mkdir(parents=True)
            (source / "nested" / "changed.md").write_text("version one", encoding="utf-8")
            (source / "removed.md").write_text("removed artifact", encoding="utf-8")

            self.assertTrue(sync_markdown_tree(source, target, history))
            (source / "nested" / "changed.md").write_text("version two", encoding="utf-8")
            (source / "removed.md").unlink()
            (source / "added.md").write_text("new artifact", encoding="utf-8")

            self.assertTrue(sync_markdown_tree(source, target, history))
            active = {path.relative_to(target).as_posix(): path.read_text(encoding="utf-8")
                      for path in target.rglob("*.md")}
            self.assertEqual(active, {
                "added.md": "new artifact",
                "nested/changed.md": "version two",
            })
            self.assertEqual(len(list(history.glob("*.md"))), 2)
            preserved = {path.read_text(encoding="utf-8") for path in history.glob("*.md")}
            self.assertEqual(preserved, {"version one", "removed artifact"})

            self.assertFalse(sync_markdown_tree(source, target, history))
            self.assertEqual(len(list(history.glob("*.md"))), 2)

    def test_failed_backup_keeps_removed_artifact_in_active_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "target"
            history = root / "history"
            source.mkdir()
            source_file = source / "removed.md"
            source_file.write_text("keep until archived", encoding="utf-8")
            sync_markdown_tree(source, target, history)
            source_file.unlink()

            with mock.patch("ctxzip_core.artifacts.atomic_copy2", side_effect=OSError("backup failed")):
                with self.assertRaisesRegex(OSError, "backup failed"):
                    sync_markdown_tree(source, target, history)

            self.assertEqual((target / "removed.md").read_text(encoding="utf-8"), "keep until archived")

    def test_incomplete_inventory_fails_before_mutating_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "target"
            history = root / "history"
            source.mkdir()
            target.mkdir()
            active = target / "kept.md"
            active.write_text("archive copy", encoding="utf-8")

            with mock.patch("ctxzip_core.artifacts.os.access", return_value=False):
                with self.assertRaisesRegex(OSError, "not readable"):
                    sync_markdown_tree(source, target, history)

            self.assertEqual(active.read_text(encoding="utf-8"), "archive copy")


if __name__ == "__main__":
    unittest.main()

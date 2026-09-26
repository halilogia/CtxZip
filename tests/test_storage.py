from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ctxzip_core import storage


class AtomicStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def temporary_files(self, target: Path) -> list[Path]:
        return list(target.parent.glob(f".{target.name}.*.tmp"))

    def test_text_replace_keeps_old_target_when_replace_fails(self):
        target = self.root / "state.json"
        target.write_text("old", encoding="utf-8")

        with patch("ctxzip_core.storage.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                storage.atomic_write_text(target, "new")

        self.assertEqual(target.read_text(encoding="utf-8"), "old")
        self.assertEqual(self.temporary_files(target), [])

    def test_json_writer_preserves_unicode_and_readable_format(self):
        target = self.root / "durum.json"

        storage.atomic_write_json(target, {"project": "İş", "count": 2})

        self.assertEqual(target.read_text(encoding="utf-8"), '{\n  "project": "İş",\n  "count": 2\n}')

    def test_copy_failure_keeps_old_target_and_cleans_partial_file(self):
        source = self.root / "source.jsonl"
        target = self.root / "raw.jsonl"
        source.write_bytes(b"complete source")
        target.write_bytes(b"previous archive")

        def write_partial_then_fail(source_file, target_file):
            target_file.write(b"partial")
            raise OSError("copy failed")

        with patch("ctxzip_core.storage.shutil.copyfileobj", side_effect=write_partial_then_fail):
            with self.assertRaises(OSError):
                storage.atomic_copy2(source, target)

        self.assertEqual(target.read_bytes(), b"previous archive")
        self.assertEqual(self.temporary_files(target), [])

    def test_copy_replaces_target_with_complete_source(self):
        source = self.root / "source.md"
        target = self.root / "transcript.md"
        source.write_bytes("özet".encode("utf-8"))
        target.write_bytes(b"old")

        storage.atomic_copy2(source, target)

        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertEqual(self.temporary_files(target), [])


if __name__ == "__main__":
    unittest.main()

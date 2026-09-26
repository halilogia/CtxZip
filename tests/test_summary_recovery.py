"""Conservative recovery of summary files not yet referenced by persisted state."""
from pathlib import Path
import tempfile
import unittest

from ctxzip_core.summary_recovery import (
    SummaryRecoveryError, next_summary_number, reconcile_orphan_summaries,
)
from ctxzip_core.summary_store import write_summary_file


class SummaryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        (self.project / "bolumler").mkdir()
        (self.project / "ciltler").mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_recovers_valid_sequential_orphan_without_rewriting_it(self):
        chapter_path = self.project / "bolumler" / "B0001.md"
        write_summary_file(
            chapter_path,
            {"tur": "bolum", "no": 1, "kaynak": "codex/session", "turlar": "T2-T5"},
            "Chapter 1",
            "Original completed summary",
        )
        previous_content = chapter_path.read_bytes()
        state = {"bolumler": [], "ciltler": []}

        changed = reconcile_orphan_summaries(self.project, state)

        self.assertTrue(changed)
        self.assertEqual(state["bolumler"], [{
            "no": 1,
            "dosya": "B0001.md",
            "oturum": "codex/session",
            "tur_baslangic": 2,
            "tur_bitis": 5,
            "cilt": None,
        }])
        self.assertEqual(chapter_path.read_bytes(), previous_content)

    def test_recovers_non_sequential_orphan_when_metadata_proves_identity(self):
        chapter_path = self.project / "bolumler" / "B0003.md"
        write_summary_file(
            chapter_path,
            {"tur": "bolum", "no": 3, "kaynak": "codex/session-3", "turlar": "T1-T4"},
            "Chapter 3",
            "Recovered non-sequential summary",
        )
        previous_content = chapter_path.read_bytes()
        state = {
            "bolumler": [{
                "no": 1, "dosya": "B0001.md", "oturum": "codex/session-1",
                "tur_baslangic": 1, "tur_bitis": 4, "cilt": None,
            }],
            "ciltler": [],
        }

        self.assertTrue(reconcile_orphan_summaries(self.project, state))
        self.assertEqual([item["no"] for item in state["bolumler"]], [1, 3])
        self.assertEqual(chapter_path.read_bytes(), previous_content)
        self.assertFalse(reconcile_orphan_summaries(self.project, state))

    def test_metadata_less_orphan_blocks_without_mutation(self):
        chapter_path = self.project / "bolumler" / "B0002.md"
        chapter_path.write_text("# Unmapped summary\n\nKeep this file", encoding="utf-8")
        previous_content = chapter_path.read_bytes()
        state = {"bolumler": [], "ciltler": []}

        with self.assertRaisesRegex(SummaryRecoveryError, "B0002.md"):
            reconcile_orphan_summaries(self.project, state)

        self.assertEqual(state, {"bolumler": [], "ciltler": []})
        self.assertEqual(chapter_path.read_bytes(), previous_content)

    def test_recovers_non_sequential_orphan_volume_from_valid_chapter_range(self):
        chapters = [
            {"no": number, "dosya": f"B{number:04d}.md", "oturum": f"codex/{number}",
             "tur_baslangic": 1, "tur_bitis": 2, "cilt": None}
            for number in (1, 2)
        ]
        volume_path = self.project / "ciltler" / "C003.md"
        write_summary_file(
            volume_path,
            {"tur": "cilt", "no": 3, "bolumler": "B1-B2"},
            "Volume 3",
            "Recovered volume",
        )
        previous_content = volume_path.read_bytes()
        state = {"bolumler": chapters, "ciltler": []}

        self.assertTrue(reconcile_orphan_summaries(self.project, state))
        self.assertEqual(state["ciltler"], [{"no": 3, "dosya": "C003.md", "bolumler": [1, 2]}])
        self.assertEqual([chapter["cilt"] for chapter in state["bolumler"]], [3, 3])
        self.assertEqual(volume_path.read_bytes(), previous_content)

    def test_next_summary_number_uses_highest_existing_number(self):
        self.assertEqual(next_summary_number([{"no": 1}, {"no": 3}]), 4)
        self.assertEqual(next_summary_number([]), 1)

    def test_blocks_inconsistent_next_chapter_without_touching_file_or_state(self):
        chapter_path = self.project / "bolumler" / "B0001.md"
        write_summary_file(
            chapter_path,
            {"tur": "cilt", "no": 1, "bolumler": "B1-B2"},
            "Misplaced Volume",
            "Do not overwrite",
        )
        previous_content = chapter_path.read_bytes()
        state = {"bolumler": [], "ciltler": []}

        with self.assertRaisesRegex(SummaryRecoveryError, "B0001.md"):
            reconcile_orphan_summaries(self.project, state)

        self.assertEqual(state, {"bolumler": [], "ciltler": []})
        self.assertEqual(chapter_path.read_bytes(), previous_content)

    def test_recovers_orphan_volume_and_assigns_its_chapters(self):
        chapters = []
        for number in (1, 2):
            name = f"B{number:04d}.md"
            write_summary_file(
                self.project / "bolumler" / name,
                {"tur": "bolum", "no": number, "kaynak": f"codex/session-{number}", "turlar": "T1-T2"},
                f"Chapter {number}",
                f"Chapter {number} summary",
            )
            chapters.append({
                "no": number, "dosya": name, "oturum": f"codex/session-{number}",
                "tur_baslangic": 1, "tur_bitis": 2, "cilt": None,
            })
        volume_path = self.project / "ciltler" / "C001.md"
        write_summary_file(
            volume_path,
            {"tur": "cilt", "no": 1, "bolumler": "B1-B2"},
            "Volume 1",
            "User-edited recovered volume",
        )
        volume_content = volume_path.read_bytes()
        state = {"bolumler": chapters, "ciltler": []}

        changed = reconcile_orphan_summaries(self.project, state)

        self.assertTrue(changed)
        self.assertEqual(state["ciltler"], [{"no": 1, "dosya": "C001.md", "bolumler": [1, 2]}])
        self.assertEqual([chapter["cilt"] for chapter in state["bolumler"]], [1, 1])
        self.assertEqual(volume_path.read_bytes(), volume_content)


if __name__ == "__main__":
    unittest.main()

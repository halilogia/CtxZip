"""Localization tests using only synthetic messages and session records."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ctxzip
from ctxzip_core import i18n
from ctxzip_core.parsers import read_session


class LocalizationTests(unittest.TestCase):
    def test_catalog_keys_and_placeholders_are_consistent(self):
        i18n.validate_catalogs()

    def test_interpolates_named_placeholders(self):
        message = i18n.translate(
            "en", "context_result", path="archive/Demo", count=3, tokens=120
        )
        self.assertEqual(message, "[context] archive/Demo (3 summaries, ~120 tokens)")

    def test_plural_catalog_falls_back_to_other_form(self):
        with (
            mock.patch.object(i18n, "_catalog_value", return_value={"other": "{{count}} items"}),
        ):
            self.assertEqual(i18n.translate("en", "test_plural", namespace="test", count=1), "1 items")
            self.assertEqual(i18n.translate("en", "test_plural", namespace="test", count=4), "4 items")

    def test_normalizes_supported_locale_variants(self):
        self.assertEqual(i18n.normalize_language("EN-us"), "en")
        self.assertEqual(i18n.normalize_language("tr_TR"), "tr")

    def test_rejects_unsupported_locale(self):
        with self.assertRaises(i18n.LocalizationError):
            i18n.normalize_language("de-DE")

    def test_cli_help_uses_selected_language(self):
        expected = {
            "en": "Interface and generated-prompt language",
            "tr": "Arayüz ve oluşturulan istem dili",
        }
        for language, text in expected.items():
            output = io.StringIO()
            with self.subTest(language=language), mock.patch.object(
                sys, "argv", ["ctxzip.py", "--language", language, "--help"]
            ), mock.patch.object(ctxzip, "load_settings", return_value={"language": "tr"}), \
                    contextlib.redirect_stdout(output), self.assertRaises(SystemExit):
                ctxzip.main()
            self.assertIn(text, output.getvalue())

    def test_knowledge_capture_help_uses_selected_language(self):
        expected = {
            "en": "Private archive project name",
            "tr": "Özel arşivdeki proje adı",
        }
        for language, text in expected.items():
            output = io.StringIO()
            with self.subTest(language=language), mock.patch.object(
                sys, "argv", ["ctxzip.py", "--language", language, "knowledge", "add", "--help"]
            ), mock.patch.object(ctxzip, "load_settings", return_value={"language": "tr"}), \
                    contextlib.redirect_stdout(output), self.assertRaises(SystemExit):
                ctxzip.main()
            self.assertIn(text, output.getvalue())

    def test_parser_localizes_generated_labels_without_changing_user_body(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "session.jsonl"
            body = "Keep this exact phrase: **Kullanıcı:** and özetleme details."
            record = {
                "type": "user",
                "timestamp": "2026-01-01T00:00:00Z",
                "message": {"content": body},
            }
            literal_marker = {
                "type": "user",
                "timestamp": "2026-01-01T00:01:00Z",
                "message": {"content": "[görsel eklendi]"},
            }
            source.write_text(json.dumps(record) + "\n" + json.dumps(literal_marker) + "\n", encoding="utf-8")

            turns, _metadata = read_session(
                "claude-code", source, {"dusunceleri_dahil_et": False}, "en"
            )

        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0].text(), f"**User:** {body}")
        self.assertEqual(turns[1].text(), "**User:** [görsel eklendi]")

    def test_transcript_headers_follow_selected_language(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "archive"
            source = archive / "Demo" / "raw" / "codex" / "synthetic.jsonl"
            source.parent.mkdir(parents=True)
            record = {
                "type": "response_item",
                "timestamp": "2026-01-01T00:00:00Z",
                "payload": {"type": "message", "role": "user", "content": [{"text": "Hello"}]},
            }
            source.write_text(json.dumps(record) + "\n", encoding="utf-8")
            settings = {"language": "en", "dusunceleri_dahil_et": False}
            with contextlib.redirect_stdout(io.StringIO()):
                ctxzip.write_transcripts(settings, archive, "Demo")
            transcript = next((archive / "Demo" / "dokum").glob("*.md"))
            english = transcript.read_text(encoding="utf-8")
            self.assertIn("Start:", english)
            self.assertIn("Raw source:", english)
            self.assertIn("**User:** Hello", english)

            settings["language"] = "tr"
            with contextlib.redirect_stdout(io.StringIO()):
                ctxzip.write_transcripts(settings, archive, "Demo")
            turkish = transcript.read_text(encoding="utf-8")
            self.assertIn("Başlangıç:", turkish)
            self.assertIn("Ham kayıt:", turkish)

    def test_turkish_api_aliases_remain_available(self):
        self.assertIs(ctxzip.topla, ctxzip.collect)
        self.assertIs(ctxzip.ayar_yukle, ctxzip.load_settings)
        self.assertEqual(ctxzip.PROMPT_SURUMU, ctxzip.PROMPT_VERSION)
        self.assertEqual(ctxzip.BOLUM_SISTEM, ctxzip.CHAPTER_SYSTEM)
        turn = ctxzip.Tur(no=7, zaman="2026-01-01")
        self.assertEqual(turn.no, 7)
        self.assertEqual(turn.zaman, "2026-01-01")
        turn.satirlar = ["legacy content"]
        self.assertEqual(turn.metin(), "legacy content")

    def test_english_settings_filename_is_primary_with_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory)
            english_settings = app_dir / "ctxzip.settings.json"
            legacy_settings = app_dir / "ctxzip_ayar.json"
            self.assertEqual(ctxzip.default_settings_path(app_dir), english_settings)
            legacy_settings.write_text('{"language":"en"}', encoding="utf-8")
            self.assertEqual(ctxzip.default_settings_path(app_dir), legacy_settings)
            self.assertEqual(ctxzip.load_settings(ctxzip.default_settings_path(app_dir))["language"], "en")
            english_settings.touch()
            self.assertEqual(ctxzip.default_settings_path(app_dir), english_settings)
            english_settings.write_text('{"language":"tr"}', encoding="utf-8")
            self.assertEqual(ctxzip.load_settings(ctxzip.default_settings_path(app_dir))["language"], "tr")


if __name__ == "__main__":
    unittest.main()

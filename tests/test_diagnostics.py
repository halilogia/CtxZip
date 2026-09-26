"""Privacy-conscious checks for the read-only doctor command."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ctxzip
from ctxzip_core.diagnostics import run_diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_diagnostics_never_return_credential_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = copy.deepcopy(ctxzip.DEFAULT_SETTINGS)
            settings["arsiv_klasoru"] = str(root / "archive")
            settings["kaynaklar"] = {"codex": [str(root)]}
            settings["llm"].update(model="local-model", api_key_env="CTXZIP_DIAGNOSTIC_SECRET")
            secret_value = "do-not-print-this-credential-123"
            checks = run_diagnostics(
                settings,
                repository_dir=root,
                environment={"CTXZIP_DIAGNOSTIC_SECRET": secret_value},
                python_version=(3, 12),
            )

        rendered = repr(checks)
        self.assertNotIn(secret_value, rendered)
        llm_check = next(item for item in checks if item.check_key == "doctor_llm")
        self.assertTrue(llm_check.values["key_present"])

    def test_invalid_settings_are_reported_without_showing_file_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings_path = Path(temporary) / "settings.json"
            settings_path.write_text('{"secret":"private-value",', encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "ctxzip.py"), "--settings", str(settings_path),
                 "--language", "en", "doctor"],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("Settings could not be loaded", completed.stdout)
        self.assertNotIn("private-value", completed.stdout)
        self.assertNotIn("private-value", completed.stderr)

    def test_doctor_does_not_create_archive_or_contact_llm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "not-created"
            settings_path = root / "settings.json"
            secret_value = "doctor-must-not-print-this-secret"
            endpoint_value = "http://127.0.0.1:1/v1?token=endpoint-secret"
            settings_path.write_text(json.dumps({
                "language": "en",
                "arsiv_klasoru": str(archive_path),
                "kaynaklar": {"codex": [str(root)]},
                "llm": {
                    "model": "local-test-model",
                    "base_url": endpoint_value,
                    "api_key_env": "CTXZIP_DIAGNOSTIC_SECRET",
                },
            }), encoding="utf-8")
            environment = os.environ.copy()
            environment["CTXZIP_DIAGNOSTIC_SECRET"] = secret_value
            completed = subprocess.run(
                [sys.executable, str(ROOT / "ctxzip.py"), "--settings", str(settings_path), "doctor"],
                cwd=root, capture_output=True, text=True, encoding="utf-8", env=environment, check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("No network or LLM endpoint was contacted", completed.stdout)
        self.assertIn("credential present: yes", completed.stdout)
        self.assertNotIn(secret_value, completed.stdout)
        self.assertNotIn(endpoint_value, completed.stdout)
        self.assertFalse(archive_path.exists())

    def test_settings_must_be_a_json_object_for_diagnostics_to_continue(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings_path = Path(temporary) / "settings.json"
            settings_path.write_text("[]", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "ctxzip.py"), "--settings", str(settings_path),
                 "--language", "en", "doctor"],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("settings could not be loaded", completed.stdout.lower())

    def test_doctor_boolean_values_follow_selected_language(self):
        for language, expected in (("en", "credential present: no"), ("tr", "kimlik bilgisi mevcut: hayır")):
            with self.subTest(language=language):
                completed = subprocess.run(
                    [sys.executable, str(ROOT / "ctxzip.py"), "--language", language, "doctor"],
                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertIn(expected, completed.stdout)


if __name__ == "__main__":
    unittest.main()

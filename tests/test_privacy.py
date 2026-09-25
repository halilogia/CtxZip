import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ctxzip
from ctxzip_core import llm
from scripts.check_staged import content_issues, path_issue

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class PrivacyTests(unittest.TestCase):
    def test_private_paths_are_blocked(self):
        for path in ("ctxzip_ayar.json", "BAGLAM.md", "raw/oturum.txt",
                     "docs/gelen/sohbet.md", "log.jsonl", ".env.local"):
            with self.subTest(path=path):
                self.assertIsNotNone(path_issue(path))
        self.assertIsNone(path_issue("README.md"))
        self.assertIsNone(path_issue(".env.example"))

    def test_secret_and_home_path_are_reported_without_value(self):
        fake = "sk-" + "A" * 32
        home = "C:" + chr(92) + "Users" + chr(92) + "Example" + chr(92) + "file"
        issues = content_issues(("key: " + fake + "\n" + home).encode())
        self.assertIn("API anahtarı", issues)
        self.assertIn("kişisel ev yolu", issues)
        self.assertNotIn(fake, repr(issues))

    def test_llm_refusal_prevents_network(self):
        settings = {"llm": {"model": "test-model", "base_url": "http://127.0.0.1:1/v1"}}
        stdin = io.StringIO()
        with mock.patch.object(ctxzip.sys, "stdin", stdin), \
             mock.patch.object(llm.urllib.request, "urlopen") as request, \
             mock.patch("builtins.print"):
            with self.assertRaises(SystemExit):
                ctxzip.llm_cagir(settings, "system", "user")
        request.assert_not_called()

    def test_preview_matches_redacted_network_body(self):
        fake = "sk-" + "B" * 32
        settings = {"llm": {"model": "test-model", "base_url": "http://127.0.0.1:1/v1"},
                    "_onayli_gonder": True}
        reply = io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
        with mock.patch.object(llm.urllib.request, "urlopen", return_value=reply) as request, \
             mock.patch("builtins.print") as printed:
            self.assertEqual(ctxzip.llm_cagir(settings, "system", "token=" + fake), "ok")
        body = json.loads(request.call_args.args[0].data.decode("utf-8"))
        preview = "\n".join(str(arg) for call in printed.call_args_list for arg in call.args)
        self.assertNotIn(fake, str(body))
        self.assertNotIn(fake, preview)
        self.assertIn("[GİZLİ]", body["messages"][1]["content"])
        self.assertIn("[GİZLİ]", preview)

    def test_copy_into_git_requires_untracked_ignored_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            target = repo / "BAGLAM.md"
            with self.assertRaises(SystemExit):
                ctxzip.kopya_git_guvenli_mi(target)
            (repo / ".gitignore").write_text("BAGLAM.md\n", encoding="utf-8")
            ctxzip.kopya_git_guvenli_mi(target)
            target.write_text("private", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "-f", "BAGLAM.md"], check=True)
            with self.assertRaises(SystemExit):
                ctxzip.kopya_git_guvenli_mi(target)

    def test_staged_guard_blocks_private_file_and_preserves_existing_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            hook = repo / ".git" / "hooks" / "pre-commit"
            original = b"#!/bin/sh\nexit 0\n"
            hook.write_bytes(original)
            installed = subprocess.run([sys.executable, str(SCRIPTS / "install_hook.py")],
                                       cwd=repo, capture_output=True)
            self.assertEqual(installed.returncode, 0, installed.stderr.decode(errors="replace"))
            self.assertEqual((hook.parent / "pre-commit.ctxzip-backup").read_bytes(), original)
            self.assertIn("check_staged.py", hook.read_text(encoding="utf-8"))
            (repo / "README.md").write_text("safe", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
            safe = subprocess.run([sys.executable, str(SCRIPTS / "check_staged.py")],
                                  cwd=repo, capture_output=True)
            self.assertEqual(safe.returncode, 0)
            (repo / "BAGLAM.md").write_text("private", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "-f", "BAGLAM.md"], check=True)
            blocked = subprocess.run([sys.executable, str(SCRIPTS / "check_staged.py")],
                                     cwd=repo, capture_output=True)
            self.assertEqual(blocked.returncode, 1)
            self.assertIn(b"BAGLAM.md", blocked.stderr)
            self.assertNotIn(b"private", blocked.stderr)


if __name__ == "__main__":
    unittest.main()

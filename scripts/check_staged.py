#!/usr/bin/env python3
"""Commit öncesinde yalnızca Git index'ine seçilmiş içerikleri denetler.

Çıktı sırın kendisini göstermez. Bu kontrol bilinmeyen sırları yakalama garantisi vermez.
"""
from __future__ import annotations

import re
import subprocess
import sys

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

PRIVATE_PARTS = {
    "ctxzip-arsiv", "ai-arsiv", "raw", "dokum", "bolumler",
    "ciltler", "gelen",
}
PRIVATE_NAMES = {"ctxzip_ayar.json", "baglam.md", "durum.json"}
PRIVATE_SUFFIXES = (".jsonl", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3")
SECRET_PATTERNS = {
    "API anahtarı": re.compile(
        rb"(?i)(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
        rb"github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{30,}|AKIA[0-9A-Z]{16})"
    ),
    "özel anahtar": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "anahtar ataması": re.compile(
        rb"(?i)(?:api[_-]?key|access[_-]?token|secret|password|passwd)"
        rb"\s*[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{16,}"
    ),
    "kişisel ev yolu": re.compile(
        rb"(?i)(?:[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\r\n]+|"
        rb"/(?:home|Users)/[^/\r\n]+)"
    ),
}


def path_issue(path: str) -> str | None:
    parts = path.replace("\\", "/").lower().split("/")
    name = parts[-1]
    if any(part in PRIVATE_PARTS for part in parts):
        return "kişisel arşiv klasörü"
    if name in PRIVATE_NAMES or name.startswith(".env") and name != ".env.example":
        return "kişisel ayar veya çıktı"
    if name.endswith(PRIVATE_SUFFIXES) or name.endswith(".key"):
        return "hassas dosya türü"
    return None


def content_issues(data: bytes) -> list[str]:
    return [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(data)]


def run_git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE)


def main() -> int:
    try:
        paths = run_git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    except (OSError, subprocess.CalledProcessError):
        print("[CtxZip koruma] Git index okunamadı; commit durduruldu.", file=sys.stderr)
        return 1
    blocked: list[tuple[str, str]] = []
    for raw_path in paths.split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        reason = path_issue(path)
        if reason:
            blocked.append((path, reason))
            continue
        try:
            content = run_git("show", f":{path}")
        except (OSError, subprocess.CalledProcessError):
            blocked.append((path, "seçilmiş içerik okunamadı"))
            continue
        blocked.extend((path, issue) for issue in content_issues(content))
    if blocked:
        print("[CtxZip koruma] Commit durduruldu. İçerikler yazdırılmadı:", file=sys.stderr)
        for path, reason in blocked:
            print(f"  {path}: {reason}", file=sys.stderr)
        print("Dosyayı index'ten çıkarıp içeriği gözden geçirin.", file=sys.stderr)
        return 1
    print("[CtxZip koruma] Seçilmiş dosyalar denetlendi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

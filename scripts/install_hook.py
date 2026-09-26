#!/usr/bin/env python3
"""Install the CtxZip guard while preserving any existing pre-commit hook."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MARKER = "# CtxZip staged privacy guard"


def main() -> None:
    git_dir = Path(subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"], text=True
    ).strip())
    hook = git_dir / "hooks" / "pre-commit"
    backup = git_dir / "hooks" / "pre-commit.ctxzip-backup"
    if hook.exists():
        current = hook.read_text(encoding="utf-8")
        if MARKER in current:
            print("CtxZip commit guard already installed.")
            return
        if backup.exists():
            raise SystemExit(f"Backup already exists; hook was not changed: {backup}")
        backup.write_bytes(hook.read_bytes())
        os.chmod(backup, hook.stat().st_mode)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\n" + MARKER + "\n"
        "ROOT=$(git rev-parse --show-toplevel) || exit 1\n"
        "if [ -n \"$CTXZIP_PYTHON\" ]; then\n"
        "  \"$CTXZIP_PYTHON\" \"$ROOT/scripts/check_staged.py\" || exit $?\n"
        "else\n"
        "  python \"$ROOT/scripts/check_staged.py\" || exit $?\n"
        "fi\n"
        + ('exec "$(dirname "$0")/pre-commit.ctxzip-backup" "$@"\n'
           if backup.exists() else "exit 0\n"),
        encoding="utf-8",
    )
    os.chmod(hook, 0o755)
    print(f"CtxZip commit guard installed: {hook}")
    if backup.exists():
        print(f"Previous hook preserved: {backup}")


if __name__ == "__main__":
    main()

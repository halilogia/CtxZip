"""Git ignore checks for context copies."""

from pathlib import Path
import subprocess

from .i18n import translate

def ensure_git_safe_copy(target: Path, language: str = "tr") -> None:
    """Copy personal context to another Git repository only when it is ignored."""
    parent = target.parent.resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return
    if result.returncode != 0:
        return
    repository = Path(result.stdout.strip()).resolve()
    relative_path = target.resolve().relative_to(repository).as_posix()
    tracked = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "--error-unmatch", "--", relative_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0
    ignored = subprocess.run(
        ["git", "-C", str(repository), "check-ignore", "--no-index", "-q", "--", relative_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0
    if tracked or not ignored:
        raise SystemExit(
            translate(language, "copy_blocked", path=target)
        )


# Backward-compatible Turkish API aliases.
kopya_git_guvenli_mi = ensure_git_safe_copy

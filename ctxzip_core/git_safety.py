"""Bağlam kopyası için Git ignore denetimi."""

from pathlib import Path
import subprocess

def kopya_git_guvenli_mi(hedef: Path) -> None:
    """Başka bir Git deposuna kişisel bağlam yalnızca ignore edilmişse kopyalanır."""
    ust = hedef.parent.resolve()
    try:
        sonuc = subprocess.run(
            ["git", "-C", str(ust), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return
    if sonuc.returncode != 0:
        return
    repo = Path(sonuc.stdout.strip()).resolve()
    goreli = hedef.resolve().relative_to(repo).as_posix()
    izlenen = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--error-unmatch", "--", goreli],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0
    yoksayilan = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--no-index", "-q", "--", goreli],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0
    if izlenen or not yoksayilan:
        raise SystemExit(
            f"Bağlam kopyalanmadı: {hedef} Git deposunda izleniyor veya ignore edilmiyor. "
            "Hedef deponun .gitignore dosyasına BAGLAM.md ekleyin ve izlenmediğini doğrulayın."
        )

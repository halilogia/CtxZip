"""Summary metadata, manual-edit detection and persisted state format."""
from pathlib import Path
import json
import re

from .text import text_hash

PLACEHOLDER = "<!-- BURAYA-YAPISTIR -->"
BURAYA = PLACEHOLDER

def load_summary_state(project_dir: Path) -> dict:
    path = project_dir / "durum.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"bolumler": [], "ciltler": []}

def save_summary_state(project_dir: Path, state: dict) -> None:
    (project_dir / "durum.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def split_summary_metadata(text: str) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}, text
    metadata = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata, text[match.end():]

def write_summary_file(path: Path, metadata: dict, title: str, body: str) -> None:
    metadata = dict(metadata, govde_hash=text_hash(body.strip()))
    header = "\n".join(f"{key}: {value}" for key, value in metadata.items())
    path.write_text(f"---\n{header}\n---\n# {title}\n\n{body.strip()}\n", encoding="utf-8")

def read_summary_body(path: Path) -> tuple[dict, str]:
    metadata, text = split_summary_metadata(path.read_text(encoding="utf-8"))
    body = re.sub(r"^# .*\n", "", text, count=1).strip()
    return metadata, body

def is_manually_edited(path: Path) -> bool:
    metadata, body = read_summary_body(path)
    return bool(metadata.get("govde_hash")) and metadata["govde_hash"] != text_hash(body)


# Backward-compatible Turkish API aliases.
durum_yukle = load_summary_state
durum_kaydet = save_summary_state
on_bilgi_ayir = split_summary_metadata
ozet_dosyasi_yaz = write_summary_file
ozet_govdesi = read_summary_body
elle_duzenlenmis = is_manually_edited

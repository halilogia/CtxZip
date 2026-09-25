"""Bilinen sır kalıplarını maskele."""

import re

GIZLI_KALIPLAR = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization)(\"?\s*[:=]\s*\"?)(Bearer\s+)?[^\s\"',}]{8,}"),
]


def gizli_temizle(metin: str) -> str:
    """Modele gönderilen ve dökümlere yazılan metinden bilinen anahtar kalıplarını siler."""
    for kalip in GIZLI_KALIPLAR:
        if kalip.groups >= 2:
            metin = kalip.sub(lambda m: m.group(1) + m.group(2) + "[GİZLİ]", metin)
        else:
            metin = kalip.sub("[GİZLİ]", metin)
    return metin

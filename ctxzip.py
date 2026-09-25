#!/usr/bin/env python3
"""CtxZip — Claude Code / Codex / Antigravity sohbetlerini proje bazında arşivler ve
Isekai Zero tarzı kademeli özetler (Bölüm → Cilt) üretir.

Katmanlar (birbirine karıştırılmaz):
  raw/          Değişmez ham geçmiş. Kaynak silinse bile arşivde kalır.
  dokum/        Okunabilir Markdown döküm (araç çıktıları atılır, ham dosyaya işaret edilir).
  bolumler/     Bölüm özetleri (Chapter). Elle düzenlenebilir; düzenlenen özet ezilmez.
  ciltler/      Cilt özetleri (Arc): birkaç bölümün üst özeti.
  BAGLAM.md     Yeni sohbete verilecek bağlam paketi (token bütçeli).

Yalnızca Python standart kütüphanesi kullanır. Kullanım: python ctxzip.py --help
Lisans: GPL-3.0 (bkz. LICENSE).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ctxzip_core.git_safety import kopya_git_guvenli_mi
from ctxzip_core.llm import llm_cagir
from ctxzip_core.privacy import gizli_temizle

SURUM = "0.1.0"
PROMPT_SURUMU = "ozet-v1"
BURAYA = "<!-- BURAYA-YAPISTIR -->"

VARSAYILAN_AYAR = {
    "arsiv_klasoru": "~/CtxZip-Arsiv",
    "kaynaklar": {
        "claude_code": ["~/.claude/projects"],
        "codex": ["$CODEX_HOME/sessions", "~/.codex/sessions"],
        "antigravity_brain": ["~/.gemini/antigravity/brain"],
    },
    # Proje adı eşleme: çalışma klasörünün adı -> arşivdeki proje adı
    "proje_takma_adlari": {},
    # Bu klasör adlarındaki oturumlar arşivlenmez (ör. ev klasörü)
    "haric_projeler": [],
    "llm": {
        "base_url": "http://127.0.0.1:20128/v1",
        "model": "",
        "api_key_env": "CTXZIP_API_KEY",
        "timeout_sn": 300,
    },
    "bolum_token": 25000,     # Bir bölüme giren yaklaşık döküm büyüklüğü
    "cilt_bolum_sayisi": 8,   # Kaç bölüm bir cilde katlanır
    "aktif_oturum_dk": 120,   # Bu kadar dakikadır değişmeyen oturum "kapanmış" sayılır
    "dusunceleri_dahil_et": False,
}

# ---------------------------------------------------------------- yardımcılar

def genislet(p: str) -> Path | None:
    if "$CODEX_HOME" in p:
        home = os.environ.get("CODEX_HOME")
        if not home:
            return None
        p = p.replace("$CODEX_HOME", home)
    return Path(os.path.expandvars(os.path.expanduser(p)))


def ayar_yukle(yol: Path) -> dict:
    ayar = json.loads(json.dumps(VARSAYILAN_AYAR))
    if yol.exists():
        kullanici = json.loads(yol.read_text(encoding="utf-8"))
        for k, v in kullanici.items():
            if isinstance(v, dict) and isinstance(ayar.get(k), dict):
                ayar[k].update(v)
            else:
                ayar[k] = v
    return ayar


def token_tahmini(metin: str) -> int:
    # Türkçe/İngilizce karışık metin için kaba tahmin (~3.5 karakter / token).
    return int(len(metin) / 3.5) + 1


def dosya_hash(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def metin_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def guvenli_ad(s: str) -> str:
    s = re.sub(r"[^\w.\-]+", "-", s, flags=re.UNICODE).strip("-")
    return s or "adsiz"


def zaman_str(ts: str | float | None) -> str:
    if ts is None:
        return ""
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return str(ts)[:16]


SISTEM_ETIKETI = re.compile(r"<(system-reminder|local-command-caveat|environment_context|user_instructions)>.*?</\1>", re.S)


def temiz_metin(s: str) -> str:
    return SISTEM_ETIKETI.sub("", s).strip()


def kisalt(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"

# ---------------------------------------------------------------- kaynak tarama

def jsonl_satirlari(p: Path):
    with p.open(encoding="utf-8", errors="replace") as f:
        for satir in f:
            satir = satir.strip()
            if not satir:
                continue
            try:
                yield json.loads(satir)
            except json.JSONDecodeError:
                continue


def claude_cwd(p: Path) -> str | None:
    for i, d in enumerate(jsonl_satirlari(p)):
        if d.get("cwd"):
            return d["cwd"]
        if i > 200:
            break
    return None


def codex_cwd(p: Path) -> str | None:
    for i, d in enumerate(jsonl_satirlari(p)):
        payload = d.get("payload") if isinstance(d.get("payload"), dict) else d
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        if cwd:
            return cwd
        # Eski format: <environment_context><cwd>...</cwd>
        s = json.dumps(d, ensure_ascii=False)
        m = re.search(r"<cwd>(.*?)</cwd>", s)
        if m:
            return m.group(1).replace("\\\\", "\\")
        if i > 50:
            break
    return None


def codex_dosyasi_mi(p: Path) -> bool:
    for i, d in enumerate(jsonl_satirlari(p)):
        if d.get("type") in ("session_meta", "response_item", "event_msg"):
            return True
        if i > 20:
            break
    return False


def proje_adi(cwd: str | None, ayar: dict) -> str | None:
    if not cwd:
        return None
    ad = re.split(r"[\\/]", cwd.rstrip("\\/"))[-1] or cwd
    if ad in ayar["haric_projeler"]:
        return None
    return guvenli_ad(ayar["proje_takma_adlari"].get(ad, ad))


def kaynaklari_bul(ayar: dict):
    """(arac, proje, oturum_id, kaynak_yolu) üretir."""
    for kok in ayar["kaynaklar"].get("claude_code", []):
        k = genislet(kok)
        if not k or not k.exists():
            continue
        for p in sorted(k.glob("*/*.jsonl")):
            proje = proje_adi(claude_cwd(p), ayar)
            if proje:
                yield "claude-code", proje, p.stem, p
    for kok in ayar["kaynaklar"].get("codex", []):
        k = genislet(kok)
        if not k or not k.exists():
            continue
        for p in sorted(k.rglob("*.jsonl")):
            proje = proje_adi(codex_cwd(p), ayar)
            if proje:
                yield "codex", proje, p.stem, p
    for kok in ayar["kaynaklar"].get("antigravity_brain", []):
        k = genislet(kok)
        if not k or not k.exists():
            continue
        # Antigravity "brain" klasörü: konuşma başına Markdown artefaktları (task, plan, walkthrough).
        # Proje bilgisi dosyalarda garanti değildir -> "antigravity" projesine düşer, takma adla eşlenebilir.
        for d in sorted(x for x in k.iterdir() if x.is_dir()):
            if any(d.glob("*.md")):
                yield "antigravity", guvenli_ad(ayar["proje_takma_adlari"].get(d.name, "antigravity")), d.name, d

# ---------------------------------------------------------------- 1) topla

def topla(ayar: dict, kok: Path) -> None:
    yeni = guncel = ayni = 0
    for arac, proje, oid, kaynak in kaynaklari_bul(ayar):
        hedef_klasor = kok / proje / "raw" / arac
        hedef_klasor.mkdir(parents=True, exist_ok=True)
        if kaynak.is_dir():
            hedef = hedef_klasor / oid
            degisti = False
            for md in kaynak.rglob("*.md"):
                h = hedef / md.relative_to(kaynak)
                if not h.exists() or h.read_bytes() != md.read_bytes():
                    h.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(md, h)
                    degisti = True
            yeni_mi = not (hedef_klasor / (oid + ".kaynak")).exists()
            (hedef_klasor / (oid + ".kaynak")).write_text(str(kaynak), encoding="utf-8")
        else:
            hedef = hedef_klasor / (oid + ".jsonl")
            yeni_mi = not hedef.exists()
            degisti = yeni_mi or hedef.stat().st_size != kaynak.stat().st_size or dosya_hash(hedef) != dosya_hash(kaynak)
            if degisti:
                if not yeni_mi and hedef.stat().st_size > kaynak.stat().st_size:
                    # Kaynak kısalmış (araç dosyayı yeniden yazmış): eski hâli sakla, hiçbir şey silinmez.
                    shutil.copy2(hedef, hedef.with_suffix(f".{int(time.time())}.onceki.jsonl"))
                shutil.copy2(kaynak, hedef)
        if yeni_mi:
            yeni += 1
        elif degisti:
            guncel += 1
        else:
            ayni += 1
    print(f"[topla] yeni: {yeni}, güncellenen: {guncel}, değişmeyen: {ayni}  ->  {kok}")

# ---------------------------------------------------------------- 2) döküm

class Tur:
    """Bir kullanıcı isteği ve ardından gelen asistan etkinliği."""

    def __init__(self, no: int, zaman: str):
        self.no = no
        self.zaman = zaman
        self.satirlar: list[str] = []

    def metin(self) -> str:
        return "\n".join(self.satirlar).strip()


def kisa_id(oid: str) -> str:
    """Oturum kimliğinin ayırt edici kısa hâli (Codex: rollout-<tarih>-<uuid> -> uuid sonu)."""
    return oid[-8:] if oid.startswith("rollout-") else oid[:8]


def arac_ozeti(ad: str, girdi) -> str:
    if not isinstance(girdi, dict):
        return kisalt(girdi, 140)
    for anahtar in ("description", "command", "file_path", "path", "pattern", "query", "url", "prompt", "skill"):
        if girdi.get(anahtar):
            return kisalt(girdi[anahtar], 140)
    return kisalt(json.dumps(girdi, ensure_ascii=False), 140)


def claude_turlari(p: Path, dusunce: bool) -> tuple[list[Tur], dict]:
    turlar: list[Tur] = []
    bilgi = {"baslangic": None, "bitis": None, "dal": None}
    tur: Tur | None = None
    bekleyen_gorsel = 0  # Görsel ile metni ayrı mesaj olarak gelirse metnin turuna eklenir

    def yeni_tur(zaman):
        nonlocal tur, bekleyen_gorsel
        tur = Tur(len(turlar) + 1, zaman)
        turlar.append(tur)
        if bekleyen_gorsel:
            tur.satirlar.append(f"_[{bekleyen_gorsel} görsel eklendi]_")
            bekleyen_gorsel = 0

    for d in jsonl_satirlari(p):
        ts = d.get("timestamp")
        if ts:
            bilgi["baslangic"] = bilgi["baslangic"] or ts
            bilgi["bitis"] = ts
        if d.get("gitBranch") and not bilgi["dal"]:
            bilgi["dal"] = d["gitBranch"]
        if d.get("isSidechain") or d.get("isMeta"):
            continue
        tip = d.get("type")
        if tip == "system" and isinstance(d.get("commandRun"), dict):
            cr = d["commandRun"]
            yeni_tur(zaman_str(ts))
            tur.satirlar.append(f"**Kullanıcı komutu:** `/{cr.get('command', '')}` {kisalt(cr.get('args', ''), 2000)}")
            continue
        mesaj = d.get("message")
        if not isinstance(mesaj, dict):
            continue
        icerik = mesaj.get("content")
        if tip == "user":
            if d.get("isCompactSummary"):
                yeni_tur(zaman_str(ts))
                tur.satirlar.append("> _[Araç kendi bağlamını sıkıştırdı; otomatik özet ham dosyada.]_")
                continue
            parcalar = []
            if isinstance(icerik, str):
                parcalar.append(temiz_metin(icerik))
            elif isinstance(icerik, list):
                sonuc_var = False
                for b in icerik:
                    bt = b.get("type")
                    if bt == "text":
                        parcalar.append(temiz_metin(b.get("text", "")))
                    elif bt == "image":
                        parcalar.append("[görsel eklendi]")
                    elif bt == "tool_result":
                        sonuc_var = True
                        if b.get("is_error") and tur:
                            c = b.get("content")
                            c = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                            tur.satirlar.append(f"  - ✗ araç hatası: {kisalt(c, 200)}")
                if sonuc_var and not any(x for x in parcalar if x and x != "[görsel eklendi]"):
                    continue
            gorsel = sum(1 for x in parcalar if x == "[görsel eklendi]")
            metin = "\n".join(x for x in parcalar if x and x != "[görsel eklendi]").strip()
            if not metin:
                bekleyen_gorsel += gorsel
                continue
            if metin.startswith("<command-") or metin.startswith("<local-command"):
                continue
            bekleyen_gorsel += gorsel
            yeni_tur(zaman_str(ts))
            tur.satirlar.append(f"**Kullanıcı:** {metin}")
        elif tip == "assistant" and isinstance(icerik, list):
            if tur is None:
                yeni_tur(zaman_str(ts))
            for b in icerik:
                bt = b.get("type")
                if bt == "text" and b.get("text", "").strip():
                    tur.satirlar.append(f"**Asistan:** {b['text'].strip()}")
                elif bt == "tool_use":
                    tur.satirlar.append(f"  - → {b.get('name')}: {arac_ozeti(b.get('name'), b.get('input'))}")
                elif bt == "thinking" and dusunce and b.get("thinking", "").strip():
                    tur.satirlar.append(f"  > _düşünce:_ {kisalt(b['thinking'], 600)}")
    return turlar, bilgi


def codex_turlari(p: Path, dusunce: bool) -> tuple[list[Tur], dict]:
    turlar: list[Tur] = []
    bilgi = {"baslangic": None, "bitis": None, "dal": None}
    tur: Tur | None = None
    for d in jsonl_satirlari(p):
        ts = d.get("timestamp")
        if ts:
            bilgi["baslangic"] = bilgi["baslangic"] or ts
            bilgi["bitis"] = ts
        payload = d.get("payload") if isinstance(d.get("payload"), dict) else d
        if d.get("type") == "session_meta":
            git = payload.get("git") or {}
            bilgi["dal"] = git.get("branch") if isinstance(git, dict) else None
            continue
        pt = payload.get("type")
        if pt == "message":
            rol = payload.get("role")
            metin = "\n".join(
                c.get("text", "") for c in payload.get("content", []) if isinstance(c, dict)
            )
            metin = temiz_metin(metin)
            if not metin or metin.startswith("<environment_context>") or metin.startswith("<user_instructions>") or metin.startswith("# AGENTS.md"):
                continue
            if rol == "user":
                tur = Tur(len(turlar) + 1, zaman_str(ts))
                turlar.append(tur)
                tur.satirlar.append(f"**Kullanıcı:** {metin}")
            elif rol == "assistant":
                if tur is None:
                    tur = Tur(1, zaman_str(ts))
                    turlar.append(tur)
                tur.satirlar.append(f"**Asistan:** {metin}")
        elif pt in ("function_call", "custom_tool_call", "local_shell_call"):
            if tur is None:
                continue
            arg = payload.get("arguments") or payload.get("input") or payload.get("action") or ""
            try:
                arg = json.loads(arg) if isinstance(arg, str) else arg
            except json.JSONDecodeError:
                pass
            tur.satirlar.append(f"  - → {payload.get('name', pt)}: {arac_ozeti(payload.get('name'), arg)}")
        elif pt == "reasoning" and dusunce and tur is not None:
            ozet = " ".join(s.get("text", "") for s in payload.get("summary", []) if isinstance(s, dict))
            if ozet.strip():
                tur.satirlar.append(f"  > _düşünce:_ {kisalt(ozet, 600)}")
    return turlar, bilgi


def antigravity_turlari(klasor: Path, _dusunce: bool) -> tuple[list[Tur], dict]:
    turlar: list[Tur] = []
    dosyalar = sorted(klasor.rglob("*.md"), key=lambda x: x.stat().st_mtime)
    for md in dosyalar:
        t = Tur(len(turlar) + 1, zaman_str(md.stat().st_mtime))
        t.satirlar.append(f"**Artefakt `{md.name}`:**\n\n{md.read_text(encoding='utf-8', errors='replace').strip()}")
        turlar.append(t)
    zamanlar = [md.stat().st_mtime for md in dosyalar]
    bilgi = {"baslangic": min(zamanlar) if zamanlar else None, "bitis": max(zamanlar) if zamanlar else None, "dal": None}
    return turlar, bilgi


def oturumlari_listele(proje_klasoru: Path):
    """(arac, oturum_id, yol) — raw/ ve elle eklenen gelen/ dosyaları."""
    raw = proje_klasoru / "raw"
    for arac in ("claude-code", "codex"):
        for p in sorted((raw / arac).glob("*.jsonl")) if (raw / arac).exists() else []:
            if ".onceki." in p.name:
                continue
            yield arac, p.stem, p
    ag = raw / "antigravity"
    if ag.exists():
        for d in sorted(x for x in ag.iterdir() if x.is_dir()):
            yield "antigravity", d.name, d
    gelen = proje_klasoru / "gelen"
    if gelen.exists():
        for p in sorted(gelen.glob("*")):
            if p.suffix.lower() in (".md", ".txt"):
                yield "elle", p.stem, p
            elif p.suffix.lower() == ".jsonl":
                # Buluttaki oturumdan indirilen ham kayıt: Codex mi Claude Code mu, içerikten anlaşılır.
                yield ("codex" if codex_dosyasi_mi(p) else "claude-code"), p.stem, p


def elle_turlari(p: Path, _dusunce: bool) -> tuple[list[Tur], dict]:
    t = Tur(1, zaman_str(p.stat().st_mtime))
    t.satirlar.append(p.read_text(encoding="utf-8", errors="replace").strip())
    return [t], {"baslangic": p.stat().st_mtime, "bitis": p.stat().st_mtime, "dal": None}


OKUYUCULAR = {"claude-code": claude_turlari, "codex": codex_turlari, "antigravity": antigravity_turlari, "elle": elle_turlari}


def oturum_oku(arac: str, yol: Path, ayar: dict):
    turlar, bilgi = OKUYUCULAR[arac](yol, ayar["dusunceleri_dahil_et"])
    return [t for t in turlar if t.metin()], bilgi


def dokum_yaz(ayar: dict, kok: Path, proje: str | None) -> None:
    for pk in proje_klasorleri(kok, proje):
        hedef = pk / "dokum"
        hedef.mkdir(exist_ok=True)
        n = 0
        for arac, oid, yol in oturumlari_listele(pk):
            turlar, bilgi = oturum_oku(arac, yol, ayar)
            if not turlar:
                continue
            bas = zaman_str(bilgi["baslangic"])
            ad = f"{bas[:10] or 'tarihsiz'}_{arac}_{kisa_id(oid)}.md"
            govde = [f"# {pk.name} — {arac} oturumu {kisa_id(oid)}",
                     f"Başlangıç: {bas} · Son: {zaman_str(bilgi['bitis'])} · Dal: {bilgi['dal'] or '-'} · Tur: {len(turlar)}",
                     f"Ham kayıt: `{yol.relative_to(pk)}`", ""]
            for t in turlar:
                govde.append(f"## [T{t.no}] {t.zaman}\n\n{t.metin()}\n")
            (hedef / ad).write_text(gizli_temizle("\n".join(govde)), encoding="utf-8")
            n += 1
        print(f"[dokum] {pk.name}: {n} oturum -> {hedef}")


def proje_klasorleri(kok: Path, proje: str | None):
    if proje:
        pk = kok / guvenli_ad(proje)
        if not pk.exists():
            sys.exit(f"Proje bulunamadı: {pk}")
        return [pk]
    return sorted(x for x in kok.iterdir() if x.is_dir() and not x.name.startswith(".")) if kok.exists() else []

# ---------------------------------------------------------------- 3) özetle

BOLUM_SISTEM = """Sen bir yapay zekâ kodlama oturumu için kayıp-farkında bağlam sıkıştırıcısın.
Yazdığın özet GERÇEĞİN KAYNAĞI DEĞİLDİR; gerçeğin kaynağı git, dosyalar ve test çıktılarıdır.
Kurallar:
- Kaynakta geçmeyen kod davranışı, test sonucu, dosya içeriği veya karar UYDURMA.
- Yalnızca önerilen/tartışılan şeyi "karar" diye yazma; kullanıcının onayladığını ayrıca belirt.
- Her kalıcı karar ve kısıt için kaynak tur numarasını [T12] biçiminde yaz; commit SHA geçiyorsa ekle.
- Test/derleme durumu kalıcı bilgi değildir: yalnızca ilgili commit/SHA ve tur ile yaz.
- Daha yeni bir olay eskisini çürütüyorsa yenisini yaz, eskisini "Geçersizleşen bilgiler"e koy.
- Başarısız denenen yaklaşımları kısaca kaydet ki tekrar denenmesin.
- Sırlar (API anahtarı, token, parola) asla yazılmaz.
- Kaynağın dilinde yaz (Türkçe konuşulduysa Türkçe). Gereksiz sohbet ayrıntısını at.
Yalnızca aşağıdaki başlıklarla Markdown döndür; boş başlığa "-" yaz:
## Amaç
## Kullanıcı kararları ve tercihleri
## Doğrulanmış olgular
## Yapılanlar ve değişen dosyalar
## Test / doğrulama durumu (SHA ile)
## Başarısız yaklaşımlar
## Açık sorular / bekleyen işler
## Sıradaki adımlar
## Geçersizleşen bilgiler"""

CILT_SISTEM = """Sen bir yapay zekâ kodlama projesinin bölüm özetlerini tek bir CİLT özetine katlıyorsun.
Girdi: kronolojik bölüm özetleri (kullanıcı tarafından düzeltilmiş olabilir; düzeltmeler önceliklidir).
Kurallar:
- Hâlâ geçerli kararları, kısıtları ve olguları kaynaklarıyla ([B3/T12], SHA) koru.
- Sonraki bir bölümde çürütülen veya tamamlanan şeyleri "Geçersizleşen / tamamlanan" altına taşı.
- Test durumlarını yalnızca en son SHA için tut.
- Tekrarları birleştir, uydurma bilgi ekleme, sırları yazma. Kaynağın dilinde yaz.
Yalnızca şu başlıklarla Markdown döndür:
## Bu ciltte ne oldu (kısa anlatı)
## Geçerli kararlar ve kısıtlar
## Kalıcı teknik bilgiler
## Son bilinen durum (SHA ile)
## Açık sorular / bekleyen işler
## Geçersizleşen / tamamlanan"""


def durum_yukle(pk: Path) -> dict:
    p = pk / "durum.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"bolumler": [], "ciltler": []}


def durum_kaydet(pk: Path, durum: dict) -> None:
    (pk / "durum.json").write_text(json.dumps(durum, ensure_ascii=False, indent=2), encoding="utf-8")


def on_bilgi_ayir(metin: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", metin, re.S)
    if not m:
        return {}, metin
    bilgi = {}
    for satir in m.group(1).splitlines():
        if ":" in satir:
            k, v = satir.split(":", 1)
            bilgi[k.strip()] = v.strip()
    return bilgi, metin[m.end():]


def ozet_dosyasi_yaz(yol: Path, bilgi: dict, baslik: str, govde: str) -> None:
    bilgi = dict(bilgi, govde_hash=metin_hash(govde.strip()))
    on = "\n".join(f"{k}: {v}" for k, v in bilgi.items())
    yol.write_text(f"---\n{on}\n---\n# {baslik}\n\n{govde.strip()}\n", encoding="utf-8")


def ozet_govdesi(yol: Path) -> tuple[dict, str]:
    bilgi, metin = on_bilgi_ayir(yol.read_text(encoding="utf-8"))
    govde = re.sub(r"^# .*\n", "", metin, count=1).strip()
    return bilgi, govde


def elle_duzenlenmis(yol: Path) -> bool:
    bilgi, govde = ozet_govdesi(yol)
    return bool(bilgi.get("govde_hash")) and bilgi["govde_hash"] != metin_hash(govde)


def tur_sinirla(metin: str, butce_token: int) -> str:
    """Bütçeyi tek başına aşan turu baştan ve sondan korunarak kısaltır (istek ve sonuç kalır)."""
    sinir = int(butce_token * 3.5)
    if len(metin) <= sinir:
        return metin
    yarim = sinir // 2
    return metin[:yarim] + f"\n\n[… {len(metin) - 2 * yarim} karakter kısaltıldı; tamamı dokum/ ve raw/ içinde …]\n\n" + metin[-yarim:]


def bolum_parcalari(turlar: list[Tur], bas_tur: int, butce: int):
    """bas_tur'dan sonraki turları bütçeye göre gruplar; tur asla bölünmez."""
    parca: list[Tur] = []
    boyut = 0
    for t in turlar:
        if t.no <= bas_tur:
            continue
        tk = token_tahmini(t.metin())
        if parca and boyut + tk > butce:
            yield parca, True
            parca, boyut = [], 0
        parca.append(t)
        boyut += tk
    if parca:
        yield parca, False


def bekleyenleri_doldur(ayar: dict, pk: Path) -> int:
    """--elle ile açılmış ama hâlâ boş olan bölüm/cilt dosyalarını LLM ile doldurur."""
    dolan = 0
    for klasor, sistem in (("bolumler", BOLUM_SISTEM), ("ciltler", CILT_SISTEM)):
        for dosya in sorted((pk / klasor).glob("*.md")) if (pk / klasor).exists() else []:
            if dosya.name.endswith(".istem.md") or BURAYA not in dosya.read_text(encoding="utf-8"):
                continue
            istem_dosyasi = dosya.with_name(dosya.stem + ".istem.md")
            if not istem_dosyasi.exists():
                continue
            istem = istem_dosyasi.read_text(encoding="utf-8").split("# KULLANICI\n\n", 1)[-1]
            try:
                govde = llm_cagir(ayar, sistem, istem)
            except RuntimeError as e:
                print(f"[ozetle] {dosya.name} doldurulamadı: {e}")
                return dolan
            bilgi, metin = on_bilgi_ayir(dosya.read_text(encoding="utf-8"))
            baslik = metin.split("\n", 1)[0].lstrip("# ").strip()
            bilgi.pop("govde_hash", None)
            ozet_dosyasi_yaz(dosya, dict(bilgi, model=ayar["llm"]["model"]), baslik, govde)
            dolan += 1
            print(f"[ozetle] {pk.name}: bekleyen {dosya.name} LLM ile dolduruldu")
    return dolan


def ozetle(ayar: dict, kok: Path, proje: str | None, elle: bool) -> None:
    for pk in proje_klasorleri(kok, proje):
        durum = durum_yukle(pk)
        bk = pk / "bolumler"
        bk.mkdir(exist_ok=True)
        if not elle and ayar["llm"].get("model"):
            bekleyenleri_doldur(ayar, pk)
        islenen = {}  # oturum anahtarı -> son özetlenen tur
        for b in durum["bolumler"]:
            anahtar = b["oturum"]
            islenen[anahtar] = max(islenen.get(anahtar, 0), b["tur_bitis"])
        oturumlar = []
        for arac, oid, yol in oturumlari_listele(pk):
            turlar, bilgi = oturum_oku(arac, yol, ayar)
            if turlar:
                oturumlar.append((str(bilgi["baslangic"] or ""), arac, oid, yol, turlar))
        oturumlar.sort(key=lambda x: zaman_str(x[0]))
        yeni = 0
        for _bas, arac, oid, yol, turlar in oturumlar:
            anahtar = f"{arac}/{oid}"
            kapanmis = (time.time() - yol.stat().st_mtime) > ayar["aktif_oturum_dk"] * 60
            for parca, dolu in bolum_parcalari(turlar, islenen.get(anahtar, 0), ayar["bolum_token"]):
                if not dolu and not kapanmis:
                    print(f"[ozetle] {pk.name}: {anahtar} hâlâ aktif, son {len(parca)} tur sonraki çalıştırmaya kaldı")
                    continue
                no = len(durum["bolumler"]) + 1
                kaynak = "\n\n".join(f"## [T{t.no}] {t.zaman}\n{tur_sinirla(t.metin(), ayar['bolum_token'])}" for t in parca)
                kaynak = gizli_temizle(kaynak)
                istem = (f"Proje: {pk.name}\nKaynak: {arac} oturumu {kisa_id(oid)}, turlar T{parca[0].no}–T{parca[-1].no}\n\n"
                         f"Önceki bölümlerle çelişki varsa belirt. Döküm:\n\n{kaynak}")
                dosya = bk / f"B{no:04d}.md"
                bilgi = {"tur": "bolum", "no": no, "kaynak": anahtar, "turlar": f"T{parca[0].no}-T{parca[-1].no}",
                         "tarih": parca[0].zaman, "kaynak_hash": metin_hash(kaynak), "prompt": PROMPT_SURUMU}
                baslik = f"Bölüm {no} — {parca[0].zaman[:10]} · {arac} {kisa_id(oid)} · T{parca[0].no}–T{parca[-1].no}"
                if elle:
                    (bk / f"B{no:04d}.istem.md").write_text(f"# SİSTEM\n\n{BOLUM_SISTEM}\n\n# KULLANICI\n\n{istem}\n", encoding="utf-8")
                    ozet_dosyasi_yaz(dosya, dict(bilgi, model="elle"), baslik,
                                     f"{BURAYA}\n`B{no:04d}.istem.md` içeriğini herhangi bir modele verin, yanıtı bu satırın yerine yapıştırın.")
                else:
                    try:
                        govde = llm_cagir(ayar, BOLUM_SISTEM, istem)
                    except RuntimeError as e:
                        print(f"[ozetle] HATA ({pk.name} B{no:04d}): {e}\n  -> --elle ile istem dosyası üretebilirsiniz.")
                        durum_kaydet(pk, durum)
                        return
                    ozet_dosyasi_yaz(dosya, dict(bilgi, model=ayar["llm"]["model"]), baslik, govde)
                durum["bolumler"].append({"no": no, "dosya": dosya.name, "oturum": anahtar,
                                          "tur_baslangic": parca[0].no, "tur_bitis": parca[-1].no, "cilt": None})
                durum_kaydet(pk, durum)
                yeni += 1
                print(f"[ozetle] {pk.name}: Bölüm {no} yazıldı ({anahtar} T{parca[0].no}–T{parca[-1].no})")
        yeni += cilt_katla(ayar, pk, durum, elle)
        durum_kaydet(pk, durum)
        if not yeni:
            print(f"[ozetle] {pk.name}: yeni bölüm/cilt yok")


def cilt_katla(ayar: dict, pk: Path, durum: dict, elle: bool) -> int:
    ck = pk / "ciltler"
    ck.mkdir(exist_ok=True)
    yeni = 0
    while True:
        bos = [b for b in durum["bolumler"] if b["cilt"] is None]
        grup = bos[: ayar["cilt_bolum_sayisi"]]
        if len(grup) < ayar["cilt_bolum_sayisi"]:
            return yeni
        bekleyen = [b for b in grup if BURAYA in (pk / "bolumler" / b["dosya"]).read_text(encoding="utf-8")]
        if bekleyen:
            print(f"[cilt] {pk.name}: {len(bekleyen)} bölüm elle doldurulmayı bekliyor, cilt ertelendi")
            return yeni
        no = len(durum["ciltler"]) + 1
        parcalar = []
        for b in grup:
            _bilgi, govde = ozet_govdesi(pk / "bolumler" / b["dosya"])
            parcalar.append(f"# Bölüm {b['no']} ({b['oturum']} T{b['tur_baslangic']}–T{b['tur_bitis']})\n{govde}")
        istem = f"Proje: {pk.name}\nBölümler B{grup[0]['no']}–B{grup[-1]['no']}:\n\n" + "\n\n".join(parcalar)
        dosya = ck / f"C{no:03d}.md"
        bilgi = {"tur": "cilt", "no": no, "bolumler": f"B{grup[0]['no']}-B{grup[-1]['no']}", "prompt": PROMPT_SURUMU}
        baslik = f"Cilt {no} — Bölüm {grup[0]['no']}–{grup[-1]['no']}"
        if elle:
            (ck / f"C{no:03d}.istem.md").write_text(f"# SİSTEM\n\n{CILT_SISTEM}\n\n# KULLANICI\n\n{istem}\n", encoding="utf-8")
            ozet_dosyasi_yaz(dosya, dict(bilgi, model="elle"), baslik, f"{BURAYA}\n`C{no:03d}.istem.md` yanıtını buraya yapıştırın.")
        else:
            try:
                govde = llm_cagir(ayar, CILT_SISTEM, istem)
            except RuntimeError as e:
                print(f"[cilt] HATA ({pk.name} C{no:03d}): {e}")
                return yeni
            ozet_dosyasi_yaz(dosya, dict(bilgi, model=ayar["llm"]["model"]), baslik, govde)
        for b in grup:
            b["cilt"] = no
        durum["ciltler"].append({"no": no, "dosya": dosya.name, "bolumler": [b["no"] for b in grup]})
        yeni += 1
        print(f"[cilt] {pk.name}: Cilt {no} yazıldı (B{grup[0]['no']}–B{grup[-1]['no']})")

# ---------------------------------------------------------------- 4) bağlam paketi

def baglam(ayar: dict, kok: Path, proje: str, butce: int, kopyala: str | None) -> None:
    pk = proje_klasorleri(kok, proje)[0]
    durum = durum_yukle(pk)
    secilen: list[tuple[str, str]] = []
    kalan = butce
    # En yeniden eskiye: önce ciltlere katlanmamış bölümler, sonra ciltler.
    adaylar = [("bolumler", b["dosya"]) for b in reversed(durum["bolumler"]) if b["cilt"] is None]
    adaylar += [("ciltler", c["dosya"]) for c in reversed(durum["ciltler"])]
    atlanan = 0
    for klasor, ad in adaylar:
        yol = pk / klasor / ad
        _bilgi, govde = ozet_govdesi(yol)
        if BURAYA in govde:
            continue
        tk = token_tahmini(govde)
        if tk > kalan:
            atlanan += 1
            continue
        baslik = yol.read_text(encoding="utf-8").split("\n# ", 1)[-1].split("\n", 1)[0]
        secilen.append((baslik, govde))
        kalan -= tk
    secilen.reverse()  # kronolojik sıra
    cikti = [f"# {pk.name} — AI oturum bağlamı",
             f"_Üretildi: {datetime.now().strftime('%Y-%m-%d %H:%M')} · {len(secilen)} özet · ~{butce - kalan} token"
             + (f" · bütçe nedeniyle {atlanan} eski özet dışarıda" if atlanan else "") + "_", "",
             "> Bu dosya önceki AI oturumlarının özetidir, **gerçeğin kaynağı değildir**. Kod, git geçmişi ve",
             "> test çıktıları ile çelişirse onlar geçerlidir. SHA'sız test durumu bilgisine güvenme.", ""]
    for baslik, govde in secilen:
        cikti.append(f"---\n\n# {baslik}\n\n{govde}\n")
    hedef = pk / "BAGLAM.md"
    hedef.write_text("\n".join(cikti), encoding="utf-8")
    print(f"[baglam] {hedef} ({len(secilen)} özet, ~{butce - kalan} token)")
    if kopyala:
        k = Path(os.path.expanduser(kopyala))
        k = k / "BAGLAM.md" if k.is_dir() else k
        kopya_git_guvenli_mi(k)
        shutil.copy2(hedef, k)
        print(f"[baglam] kopyalandı -> {k}")

# ---------------------------------------------------------------- durum

def listele(kok: Path) -> None:
    if not kok.exists():
        print(f"Arşiv yok: {kok}  (önce: python ctxzip.py topla)")
        return
    print(f"{'Proje':32} {'Oturum':>6} {'Bölüm':>6} {'Cilt':>5} {'Bekleyen':>8} {'Düzeltilen':>10}")
    for pk in proje_klasorleri(kok, None):
        oturum = sum(1 for _ in oturumlari_listele(pk))
        durum = durum_yukle(pk)
        bekleyen = sum(1 for b in durum["bolumler"]
                       if (pk / "bolumler" / b["dosya"]).exists() and BURAYA in (pk / "bolumler" / b["dosya"]).read_text(encoding="utf-8"))
        # Elle düzeltilen özet oranı, özet kalitesinin en değerli geri bildirimidir.
        duzeltilen = sum(1 for k in ("bolumler", "ciltler") for f in (pk / k).glob("*.md")
                         if (pk / k).exists() and not f.name.endswith(".istem.md") and elle_duzenlenmis(f))
        print(f"{pk.name[:32]:32} {oturum:>6} {len(durum['bolumler']):>6} {len(durum['ciltler']):>5} {bekleyen:>8} {duzeltilen:>10}")


def main() -> None:
    ap = argparse.ArgumentParser(description="CtxZip — AI sohbet arşivi ve Isekai tarzı kademeli özetleyici")
    ap.add_argument("--ayar", default=str(Path(__file__).with_name("ctxzip_ayar.json")), help="ayar dosyası")
    alt = ap.add_subparsers(dest="komut", required=True)
    alt.add_parser("topla", help="Claude Code / Codex / Antigravity oturumlarını arşive kopyalar")
    d = alt.add_parser("dokum", help="Ham oturumlardan okunabilir Markdown döküm üretir")
    d.add_argument("--proje")
    o = alt.add_parser("ozetle", help="Yeni turlardan bölüm, dolan bölümlerden cilt üretir")
    o.add_argument("--proje")
    o.add_argument("--elle", action="store_true", help="LLM çağırma; istem dosyası üret, yanıtı sen yapıştır")
    o.add_argument("--onayli-gonder", action="store_true",
                   help="LLM önizlemesini göster; etkileşimli onayı atla (otomasyon için)")
    b = alt.add_parser("baglam", help="Yeni sohbet için bütçeli bağlam paketi (BAGLAM.md)")
    b.add_argument("proje")
    b.add_argument("--token", type=int, default=12000)
    b.add_argument("--kopyala", help="BAGLAM.md'nin kopyalanacağı klasör/dosya (ör. proje klasörü)")
    h = alt.add_parser("hepsi", help="topla + dokum + ozetle")
    h.add_argument("--elle", action="store_true")
    h.add_argument("--onayli-gonder", action="store_true",
                   help="LLM önizlemesini göster; etkileşimli onayı atla (otomasyon için)")
    alt.add_parser("durum", help="Projeleri ve özet sayılarını listeler")
    arg = ap.parse_args()

    ayar = ayar_yukle(Path(arg.ayar))
    ayar["_onayli_gonder"] = getattr(arg, "onayli_gonder", False)
    kok = genislet(ayar["arsiv_klasoru"])
    kok.mkdir(parents=True, exist_ok=True)
    if arg.komut == "topla":
        topla(ayar, kok)
    elif arg.komut == "dokum":
        dokum_yaz(ayar, kok, arg.proje)
    elif arg.komut == "ozetle":
        ozetle(ayar, kok, arg.proje, arg.elle)
    elif arg.komut == "baglam":
        baglam(ayar, kok, arg.proje, arg.token, arg.kopyala)
    elif arg.komut == "hepsi":
        topla(ayar, kok)
        dokum_yaz(ayar, kok, None)
        ozetle(ayar, kok, None, arg.elle)
    elif arg.komut == "durum":
        listele(kok)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

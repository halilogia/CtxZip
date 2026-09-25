"""LLM önizleme, onay ve ağ gönderimi."""

import json
import os
import re
import sys
import urllib.error
import urllib.request

from .privacy import gizli_temizle

def llm_cagir(ayar: dict, sistem: str, kullanici: str) -> str:
    llm = ayar["llm"]
    model = llm.get("model", "").strip()
    if not model or model == "BURAYA-9ROUTER-MODEL-ADI":
        raise RuntimeError("llm.model ayarlı değil; model adını yazın veya --elle kullanın")
    url = llm["base_url"].rstrip("/").replace("://localhost", "://127.0.0.1") + "/chat/completions"
    # Önizlemede görülen metin ile ağ isteğine giren metin bire bir aynı olmalı.
    sistem = gizli_temizle(sistem)
    kullanici = gizli_temizle(kullanici)
    print(f"\n[LLM önizleme] Hedef: {url} · Model: {model}")
    print(f"--- SİSTEM ({len(sistem)} karakter) ---\n{sistem}")
    print(f"--- KULLANICI ({len(kullanici)} karakter) ---\n{kullanici}")
    print("--- ÖNİZLEME SONU ---", flush=True)
    if not ayar.get("_onayli_gonder", False):
        if not sys.stdin.isatty():
            raise SystemExit("LLM isteği gönderilmedi: etkileşimli onay yok. "
                             "Denetledikten sonra --onayli-gonder kullanın.")
        try:
            cevap = input("Bu metin belirtilen sağlayıcıya gönderilsin mi? [e/H]: ").strip().lower()
        except EOFError:
            cevap = ""
        if cevap not in ("e", "evet"):
            raise SystemExit("LLM isteği kullanıcı tarafından iptal edildi.")
    govde = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": kullanici}],
        "temperature": 0.2,
        "stream": False,
    }).encode("utf-8")
    basliklar = {"Content-Type": "application/json", "Connection": "close"}
    anahtar = os.environ.get(llm.get("api_key_env") or "CTXZIP_API_KEY", "")
    if anahtar:
        basliklar["Authorization"] = "Bearer " + anahtar
    istek = urllib.request.Request(url, data=govde, headers=basliklar, method="POST")
    try:
        with urllib.request.urlopen(istek, timeout=llm.get("timeout_sn", 300)) as r:
            veri = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Bağlanılamadı: {e.reason}") from None
    icerik = (veri.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not icerik or not icerik.strip():
        raise RuntimeError("Model boş yanıt döndü")
    return re.sub(r"^\s*<think>.*?</think>", "", icerik, flags=re.S).strip()

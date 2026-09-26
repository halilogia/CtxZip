"""LLM preview, approval, and network requests."""

import json
import os
import re
import sys
import urllib.error
import urllib.request

from .privacy import redact_secrets
from .i18n import translate

SAMPLE_MODEL_VALUES = {"YOUR-LLM-MODEL", "BURAYA-9ROUTER-MODEL-ADI"}

def call_llm(settings: dict, system_prompt: str, user_prompt: str) -> str:
    language = settings.get("language", "tr")
    llm_settings = settings["llm"]
    model = llm_settings.get("model", "").strip()
    if not model or model in SAMPLE_MODEL_VALUES:
        raise RuntimeError(translate(language, "llm_model_missing"))
    url = llm_settings["base_url"].rstrip("/").replace("://localhost", "://127.0.0.1") + "/chat/completions"
    # The text shown in the preview must exactly match the text sent in the request.
    system_prompt = redact_secrets(system_prompt, language)
    user_prompt = redact_secrets(user_prompt, language)
    print(translate(language, "llm_preview", url=url, model=model))
    print(f"--- {translate(language, 'system')} ({len(system_prompt)} {translate(language, 'characters')}) ---\n{system_prompt}")
    print(f"--- {translate(language, 'user')} ({len(user_prompt)} {translate(language, 'characters')}) ---\n{user_prompt}")
    print(translate(language, "preview_end"), flush=True)
    if not settings.get("_onayli_gonder", False):
        if not sys.stdin.isatty():
            raise SystemExit(translate(language, "approval_required"))
        try:
            response = input(translate(language, "approval_prompt")).strip().lower()
        except EOFError:
            response = ""
        accepted = ("y", "yes") if language == "en" else ("e", "evet")
        if response not in accepted:
            raise SystemExit(translate(language, "request_cancelled"))
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "temperature": 0.2,
        "stream": False,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "Connection": "close"}
    api_key = os.environ.get(llm_settings.get("api_key_env") or "CTXZIP_API_KEY", "")
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=llm_settings.get("timeout_sn", 300)) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(translate(language, "connection_failed", reason=e.reason)) from None
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not content or not content.strip():
        raise RuntimeError(translate(language, "empty_model_reply"))
    return re.sub(r"^\s*<think>.*?</think>", "", content, flags=re.S).strip()


# Backward-compatible Turkish API aliases.
llm_cagir = call_llm

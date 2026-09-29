from __future__ import annotations

import copy
import re
import time

import requests

_ORIGINAL_POST = requests.post
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_LAST_GROQ_REQUEST_AT = 0.0

QUALITY_APPENDIX = """
ZORUNLU KALITE KAPISI:
- 10 aday soru üret; sistem en iyi ve mümkün olduğunca farklı türdeki 3 tanesini seçecek.
- Her aday için cevabı önce kendi içinde çöz ve doğrula.
- Cevabından emin değilsen o soruyu hiç yazma.
- Mantık hatası, yanlış cevap, eksik bilgi, yarım kalan hikaye, çok karmaşık/uzun kurgu, tartışmalı yorum veya birden fazla doğru cevap varsa o soruyu yazma.
- Soru 160 karakteri geçmesin ve tamamlanmış net bir soru olsun.
- Cevap kısa olabilir; fakat answer ile explanation birbiriyle çelişmemeli.
- Explanation, answer'ın neden doğru olduğunu açıkça kanıtlamalı.
- İlk üç aday en merak uyandıran, yorumda tahmin ettiren sorular olsun.
- Sadece JSON döndür.
""".strip()


def guarded_post(url, *args, **kwargs):
    global _LAST_GROQ_REQUEST_AT
    if url != GROQ_CHAT_URL:
        return _ORIGINAL_POST(url, *args, **kwargs)

    call_kwargs = copy.deepcopy(kwargs)
    body = call_kwargs.get("json")
    if isinstance(body, dict):
        body["temperature"] = min(float(body.get("temperature", 0.8)), 0.65)
        body.pop("max_tokens", None)
        body["max_completion_tokens"] = 2048
        body["reasoning_effort"] = "low"
        messages = body.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                content = str(last.get("content", ""))
                if "katı bir Türkçe quiz doğrulayıcısısın" not in content:
                    last["content"] = f"{content}\n\n{QUALITY_APPENDIX}"
        call_kwargs["json"] = body

    response = None
    for attempt in range(3):
        wait = max(0.0, 23.0 - (time.monotonic() - _LAST_GROQ_REQUEST_AT))
        if wait:
            time.sleep(wait)
        _LAST_GROQ_REQUEST_AT = time.monotonic()
        response = _ORIGINAL_POST(url, *args, **call_kwargs)
        if response.status_code != 429 or attempt == 2:
            return response
        retry_after = response.headers.get("Retry-After", "")
        if not retry_after:
            match = re.search(r"try again in ([0-9.]+)s", response.text or "", re.IGNORECASE)
            retry_after = match.group(1) if match else str(5 * (attempt + 1))
        try:
            delay = min(30.0, max(1.0, float(retry_after) + 0.5))
        except ValueError:
            delay = float(5 * (attempt + 1))
        _LAST_GROQ_REQUEST_AT = time.monotonic() - 23.0 + delay
    return response


requests.post = guarded_post

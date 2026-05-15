from __future__ import annotations

import copy

import requests

_ORIGINAL_POST = requests.post
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

QUALITY_APPENDIX = """

ZORUNLU KALITE KAPISI:
- 10 aday soru üret; sistem en iyi 3 tanesini seçecek.
- Her aday için cevabı önce kendi içinde çöz ve doğrula.
- Cevabından emin değilsen o soruyu hiç yazma.
- Mantık hatası, yanlış cevap, eksik bilgi, yarım kalan hikaye, çok karmaşık/uzun kurgu, tartışmalı yorum veya birden fazla doğru cevap varsa o soruyu yazma.
- Soru 160 karakteri geçmesin ve tamamlanmış net bir soru olsun.
- Cevap kısa olabilir; fakat answer ile explanation birbiriyle çelişmemeli.
- Explanation, answer'ın neden doğru olduğunu açıkça kanıtlamalı.
- Sadece JSON döndür.
""".strip()


def guarded_post(url, *args, **kwargs):
    if url == GROQ_CHAT_URL:
        call_kwargs = copy.deepcopy(kwargs)
        body = call_kwargs.get("json")
        if isinstance(body, dict):
            body["temperature"] = min(float(body.get("temperature", 0.8)), 0.65)
            body["max_tokens"] = max(int(body.get("max_tokens", 1100)), 3000)
            messages = body.get("messages")
            if isinstance(messages, list) and messages:
                last = messages[-1]
                if isinstance(last, dict):
                    last["content"] = f"{last.get('content', '')}\n\n{QUALITY_APPENDIX}"
            call_kwargs["json"] = body
        return _ORIGINAL_POST(url, *args, **call_kwargs)
    return _ORIGINAL_POST(url, *args, **kwargs)


requests.post = guarded_post

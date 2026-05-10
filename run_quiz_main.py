#!/usr/bin/env python3
"""Quizdenede wrapper: main.py render/altyazı/TTS sistemi aynı kalır.
Sadece içerik, Groq soruları ve Pexels aramaları quiz konusuna çevrilir.
YouTube upload varsayılan olarak kapalıdır; videolar GitHub Actions artifact/release olarak indirilir.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
from typing import Any

# main.py import edilirken YouTube kontrolüne takılmamak için dummy değer.
os.environ.setdefault("YOUTUBE_REFRESH_TOKEN", "youtube_upload_disabled")

import requests

import main as bot

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
ENABLE_YOUTUBE_UPLOAD = os.getenv("ENABLE_YOUTUBE_UPLOAD", "0") == "1"
_ORIGINAL_UPDATE_HISTORY = bot.update_history
_ORIGINAL_UPLOAD_TO_YOUTUBE = bot.upload_to_youtube
bot.YOUTUBE_CATEGORY_ID = "27"

VIRAL_PREFIX_PATTERNS = [
    r"^yetişkinlerin\s*%?\s*90[ıi']*\s*bu\s*soruyu\s*çözemiyor\s*[:\-.!?]*\s*",
    r"^yetişkinlerin\s*yüzde\s*doksan[ıi']*\s*bu\s*soruyu\s*çözemiyor\s*[:\-.!?]*\s*",
    r"^bu\s*soruyu\s*çözebilir\s*misin\s*[:\-.!?]*\s*",
    r"^soru\s*(geliyor)?\s*[:\-.!?]*\s*",
]


def _qid(question: str, answer: str) -> str:
    return hashlib.sha1(f"{question}|{answer}".encode("utf-8")).hexdigest()


def _json_from_text(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?", "", text.strip()).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("JSON bulunamadı")
    return json.loads(text[start:end + 1])


def _clean_question(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text).strip())
    for pattern in VIRAL_PREFIX_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = text.strip(" \n\t:-—.!?")
    if text and not text.endswith("?"):
        text += "?"
    return text[:220]


def _clean_answer(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text).strip())
    text = re.sub(r"^(cevap|yanıt)\s*[:\-.]*\s*", "", text, flags=re.IGNORECASE)
    return text.strip()[:140]


def _recent(history: dict[str, Any], limit: int = 80) -> list[str]:
    out = []
    for item in history.get("processed_news", [])[-limit:]:
        if item.get("title"):
            out.append(str(item["title"]))
    for item in history.get("processed_questions", [])[-limit:]:
        if item.get("question"):
            out.append(str(item["question"]))
    return out[-limit:]


def _previous_answer(history: dict[str, Any]) -> str:
    items = history.get("processed_questions", [])
    if not items:
        return "İlk video olduğu için önceki cevap yok."
    answer = _clean_answer(items[-1].get("answer", ""))
    return answer or "Önceki cevap bulunamadı."


def _fallback() -> list[dict[str, str]]:
    pool = [
        {"topic": "dikkat", "question": "Bir kelimeyi yanlış yazarsan ve o kelime 'yanlış' kelimesiyse, kelime doğru mu yazılmış olur?", "answer": "Hayır, yine yanlış yazılmış olur.", "explanation": "Kelimenin anlamı değil, yazım biçimi önemlidir."},
        {"topic": "mantık", "question": "Bir odada üç lamba var, dışarıda üç anahtar var. Odaya sadece bir kez girerek hangi anahtarın hangi lambaya ait olduğunu nasıl anlarsın?", "answer": "Birini uzun süre açık bırak, kapat; ikincisini açık bırak; üçüncüye dokunma.", "explanation": "İçeride yanan lamba ikinci anahtar, sıcak ama sönük lamba birinci, soğuk sönük lamba üçüncüdür."},
        {"topic": "kelime oyunu", "question": "Hangi soru ne kadar doğru cevaplanırsa cevaplansın, cevabı her zaman değişir?", "answer": "Saat kaç?", "explanation": "Zaman ilerlediği için aynı sorunun cevabı sürekli değişir."},
        {"topic": "günlük hayat yanılgısı", "question": "Bir kitabın 100. sayfasını çevirdikten hemen sonra gördüğün sayfa tek mi çift mi olur?", "answer": "Tek olur.", "explanation": "Kitaplarda sağ sayfalar genelde tek, sol sayfalar çift numaradır."},
        {"topic": "hızlı akıl yürütme", "question": "Bir sınıfta herkes en az bir kişiyi tanıyor. Bu, herkesin herkesi tanıdığı anlamına gelir mi?", "answer": "Hayır.", "explanation": "Bir kişiyi tanımak, sınıftaki herkesle bağlantılı olmak demek değildir."},
    ]
    random.shuffle(pool)
    return pool[:3]


def _generate(history: dict[str, Any]) -> list[dict[str, str]]:
    if not GROQ_API_KEY:
        return _fallback()
    prompt = f"""
Türkçe Shorts için 3 kaliteli beyin cimnastiği sorusu üret.

Önemli format kuralı:
- question alanına SADECE sorunun kendisini yaz.
- question alanında 'Yetişkinlerin yüzde 90ı', 'bu soruyu çözemiyor', 'soru geliyor' gibi video giriş cümleleri ASLA olmasın.
- answer alanına sadece kısa cevabı yaz.

Kalite kuralları:
- Aşırı bilinen internet bilmeceleri üretme.
- Sorular özgün, düşündürücü ve adil olsun.
- Matematik ağırlıklı olmasın; en fazla 1 küçük hesap olabilir.
- Türler: dikkat, mantık, kelime oyunu, günlük hayat yanılgısı, unutulan temel bilgi, hızlı akıl yürütme.
- Soru kısa, net, cevap tek ve tartışmasız olsun.
- Tuzaklı olsun ama haksız/uydurma olmasın.
- Her soru Türkçe olsun.
- Bunlara benzer üretme: {_recent(history)}

Sadece JSON döndür:
{{"questions":[{{"topic":"dikkat","question":"sadece gerçek soru","answer":"kısa cevap","explanation":"kısa açıklama"}}]}}
""".strip()
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "Sen özgün, adil ve kaliteli Türkçe beyin cimnastiği soruları üreten bir editörsün. Viral giriş cümlesi yazma; sadece soru üret."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.85,
                "max_tokens": 1100,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        response.raise_for_status()
        raw = _json_from_text(response.json()["choices"][0]["message"]["content"]).get("questions", [])
    except Exception as exc:
        bot.logger.warning("Groq soru üretimi başarısız, fallback kullanılıyor: %s", exc)
        raw = _fallback()

    cleaned, seen = [], set()
    for item in raw + _fallback():
        question = _clean_question(item.get("question", ""))
        answer = _clean_answer(item.get("answer", ""))
        explanation = re.sub(r"\s+", " ", str(item.get("explanation", "")).strip())[:260]
        if not question or not answer or not explanation:
            continue
        qid = _qid(question, answer)
        if qid in seen:
            continue
        seen.add(qid)
        cleaned.append({"id": qid, "topic": str(item.get("topic", "beyin cimnastiği"))[:60], "question": question, "answer": answer, "explanation": explanation})
        if len(cleaned) == 3:
            break
    return cleaned


def _items(questions: list[dict[str, str]]) -> list[dict[str, Any]]:
    now_iso = bot.now_tr().isoformat()
    out = []
    for index, q in enumerate(questions, start=1):
        title = f"Yetişkinlerin yüzde 90'ı bu soruyu çözemiyor: {q['question']}"
        out.append({
            "title": title,
            "summary": "Cevap bir sonraki videoda. Daha fazla soru için takip et.",
            "url": f"quizdenede://brain-teaser/{q['id']}",
            "query": q["topic"],
            "source": "Groq Brain Teaser",
            "published_at": now_iso,
            "fingerprint": _qid(title, q["answer"]),
            "viral_score": 100 - index,
            "quiz": q,
        })
    return out


def fetch_news_pool(hours_back: int = 20) -> list[dict[str, Any]]:
    history = bot.load_json(bot.HISTORY_FILE, {"processed_news": [], "processed_questions": []})
    return _items(_generate(history))


def choose_top_three(news: list[dict[str, Any]], history: dict[str, Any]) -> list[dict[str, Any]]:
    old = {item.get("fingerprint") for item in history.get("processed_news", [])}
    selected = [item for item in news if item.get("fingerprint") not in old][:3] or news[:3]
    prev = _previous_answer(history)
    for item in selected:
        quiz = item.get("quiz", {})
        quiz["previous_answer_text"] = prev
        prev = _clean_answer(quiz.get("answer", "")) or prev
    return selected


def generate_news_script(item: dict[str, Any]) -> str:
    quiz = item.get("quiz", {})
    question = _clean_question(quiz.get("question", item["title"]))
    previous_answer = _clean_answer(quiz.get("previous_answer_text", "")) or "İlk video olduğu için önceki cevap yok."
    return (
        "Yetişkinlerin yüzde 90'ı bu soruyu çözemiyor. "
        f"{question} "
        "Cevap bir sonraki videoda. "
        "Daha fazla soru için takip et. "
        f"Önceki videodaki sorunun cevabı: {previous_answer}"
    )


def build_background_queries(item: dict[str, Any]) -> list[str]:
    topic = str(item.get("query", "")).lower()
    base = ["brain puzzle", "thinking student", "question mark background", "quiz show lights", "logic puzzle", "student exam desk", "education learning"]
    if "kelime" in topic:
        base[:0] = ["letters typography", "word game", "alphabet background"]
    elif "dikkat" in topic:
        base[:0] = ["focus attention", "magnifying glass", "thinking face"]
    elif "mantık" in topic:
        base[:0] = ["logic puzzle", "chess thinking", "brainstorm"]
    elif "yanılgı" in topic or "günlük" in topic:
        base[:0] = ["daily life thinking", "people thinking", "confused person"]
    return list(dict.fromkeys(base))


def update_history(history: dict[str, Any], selected: list[dict[str, Any]]) -> dict[str, Any]:
    history = _ORIGINAL_UPDATE_HISTORY(history, selected)
    history.setdefault("processed_questions", [])
    for item in selected:
        quiz = item.get("quiz", {})
        if quiz:
            history["processed_questions"].append({
                "id": quiz.get("id"),
                "topic": quiz.get("topic"),
                "question": _clean_question(quiz.get("question", "")),
                "answer": _clean_answer(quiz.get("answer", "")),
                "explanation": quiz.get("explanation"),
                "used_at": bot.now_tr().isoformat(),
                "youtube_url": item.get("youtube_url"),
            })
    history["processed_questions"] = history["processed_questions"][-500:]
    return history


def upload_to_youtube(video_path, item, publish_at):
    if ENABLE_YOUTUBE_UPLOAD:
        quiz = item.get("quiz", {})
        item["title"] = "Yetişkinlerin %90'ı Bu Soruyu Çözemiyor #shorts"
        item["summary"] = f"Soru: {_clean_question(quiz.get('question', ''))}\nCevap bir sonraki videoda.\nÖnceki cevap: {_clean_answer(quiz.get('previous_answer_text', ''))}"
        return _ORIGINAL_UPLOAD_TO_YOUTUBE(video_path, item, publish_at)

    video_path = str(video_path)
    bot.logger.info("YouTube upload kapalı. Video artifact/release olarak saklanacak: %s", video_path)
    return {
        "video_id": "youtube_upload_disabled",
        "youtube_url": f"GitHub Release/Artifact: {video_path}",
        "publish_at_local": publish_at.isoformat(),
        "publish_at_utc": publish_at.astimezone(bot.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


bot.fetch_news_pool = fetch_news_pool
bot.choose_top_three = choose_top_three
bot.generate_news_script = generate_news_script
bot.build_background_queries = build_background_queries
bot.update_history = update_history
bot.upload_to_youtube = upload_to_youtube
bot.main()

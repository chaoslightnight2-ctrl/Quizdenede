#!/usr/bin/env python3
"""Quizdenede wrapper.

main.py render, TTS ve altyazı senkron sistemi aynen kullanılır.
Bu dosya sadece Groq soru üretimini, video metnini ve Pexels arama kelimelerini değiştirir.
Fallback yoktur. Groq yeni ve kaliteli 3 soru üretmezse workflow hata verir.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

os.environ.setdefault("YOUTUBE_REFRESH_TOKEN", "youtube_upload_disabled")

import requests
import main as bot

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
_ORIGINAL_UPDATE_HISTORY = bot.update_history
bot.YOUTUBE_CATEGORY_ID = "27"


BAD_QUESTION_PATTERNS = [
    r"bir saatlik yolu\s+1\s+saatte",
    r"hangi kelimenin yazılışında",
    r"hangi kelimede",
    r"kaç tane harf",
    r"hangisinde ['\"]?[a-zçğıöşü]['\"]? harfi yoktur",
]


def norm(text: str) -> str:
    text = str(text).lower().strip()
    text = text.translate(str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def make_id(question: str, answer: str) -> str:
    return hashlib.sha1(f"{norm(question)}|{norm(answer)}".encode("utf-8")).hexdigest()


def clean_question(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text).strip())
    text = re.sub(r"^yetişkinlerin\s*(%?90|yüzde\s*doksan)[^:?.!]*[:?.!\-]*\s*", "", text, flags=re.I)
    text = re.sub(r"^(bu soruyu çözebilir misin|soru geliyor|soru)[:?.!\-]*\s*", "", text, flags=re.I)
    text = text.strip(" \n\t:-—.!?")
    if text and not text.endswith("?"):
        text += "?"
    return text[:220]


def clean_answer(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text).strip())
    text = re.sub(r"^(cevap|yanıt)\s*[:\-.]*\s*", "", text, flags=re.I)
    return text.strip()[:140]


def parse_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?", "", text.strip()).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError("Groq JSON formatında cevap vermedi.")
    return json.loads(text[start:end + 1])


def is_good_question(question: str, answer: str, explanation: str) -> tuple[bool, str]:
    qn = norm(question)
    an = norm(answer)
    if len(question) < 28:
        return False, "soru çok kısa"
    if len(answer) < 2:
        return False, "cevap çok kısa"
    if len(explanation) < 20:
        return False, "açıklama çok kısa"
    for pattern in BAD_QUESTION_PATTERNS:
        if re.search(pattern, qn, flags=re.I):
            return False, f"kalitesiz/belirsiz pattern: {pattern}"
    if "hangi" in qn and "harfi" in qn and ("hangisinde" in qn or "hangisinde" in qn):
        return False, "harf sayma/seçenek sorusu belirsiz"
    if re.search(r"\b1\s+saatte\b", qn) and re.search(r"\bkaç\s+saat\b", qn):
        return False, "aşırı düz süre hesabı"
    if any(word in an for word in ["değişir", "birden fazla", "herhangi", "kişiye göre"]):
        return False, "cevap tek ve net görünmüyor"
    return True, "ok"


def used_questions(history: dict[str, Any]) -> set[str]:
    used: set[str] = set()
    for item in history.get("processed_questions", []):
        q = clean_question(item.get("question", ""))
        if q:
            used.add(norm(q))
    for item in history.get("processed_news", []):
        title = str(item.get("title", ""))
        title = re.sub(r"^Yetişkinlerin yüzde 90'ı bu soruyu çözemiyor:\s*", "", title, flags=re.I)
        q = clean_question(title)
        if q:
            used.add(norm(q))
    return used


def recent_list(history: dict[str, Any], limit: int = 150) -> list[str]:
    out: list[str] = []
    for item in history.get("processed_questions", [])[-limit:]:
        q = clean_question(item.get("question", ""))
        if q:
            out.append(q)
    return out[-limit:]


def previous_answer(history: dict[str, Any]) -> str:
    items = history.get("processed_questions", [])
    if not items:
        return "İlk video olduğu için önceki cevap yok."
    return clean_answer(items[-1].get("answer", "")) or "Önceki cevap bulunamadı."


def generate_questions(history: dict[str, Any]) -> list[dict[str, str]]:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY yok. Fallback kapalı; soru üretimi durduruldu.")

    forbidden = recent_list(history)
    prompt = f"""
Türkçe Shorts için 3 kaliteli beyin cimnastiği sorusu üret.

Kesin format:
- question: sadece sorunun kendisi. Video girişi yazma.
- answer: sadece kısa cevap.
- explanation: cevabın neden doğru olduğunu kısa açıkla.

Kalite filtresi:
- Klasik tuzak soru olabilir; klasik olması sorun değil.
- Ama çocukça kolay, cevabı bariz, iki doğru cevabı olan veya sınırsız cevabı olan soru üretme.
- 'Hangi kelimede hangi harf yoktur?' gibi belirsiz sorular üretme.
- '1 saatlik yolu 1 saatte giderse kaç saat?' gibi dümdüz hesap üretme.
- Sorunun doğru cevabı tek, net ve tartışmasız olmalı.
- İzleyici cevabı duyunca 'mantıklıymış' demeli, 'bu ne saçma' dememeli.
- En fazla 1 küçük hesap sorusu olabilir.
- Türleri karıştır: kaliteli klasik dikkat, mantık, günlük hayat yanılgısı, unutulan temel bilgi, hızlı akıl yürütme.
- Çok bilinen klasiklerden en fazla 1 tane üret; diğerleri daha iyi varyasyon olsun.
- Şu soruların aynısını veya çok benzerini ASLA üretme: {forbidden}

Sadece JSON döndür:
{{"questions":[{{"topic":"kaliteli mantık","question":"sadece soru","answer":"kısa cevap","explanation":"kısa açıklama"}}]}}
""".strip()

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "Sen kaliteli Türkçe dikkat ve mantık soruları üreten editörsün. Sorular tek cevaplı, adil ve izleyiciyi tatmin eden sorular olmalı. Zayıf, çocukça kolay veya belirsiz soru üretme."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.72,
            "max_tokens": 1100,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    response.raise_for_status()
    raw = parse_json(response.json()["choices"][0]["message"]["content"]).get("questions", [])

    used = used_questions(history)
    batch: set[str] = set()
    result: list[dict[str, str]] = []
    rejected: list[str] = []
    for item in raw:
        q = clean_question(item.get("question", ""))
        a = clean_answer(item.get("answer", ""))
        e = re.sub(r"\s+", " ", str(item.get("explanation", "")).strip())[:260]
        key = norm(q)
        ok, reason = is_good_question(q, a, e)
        if not ok:
            rejected.append(f"{reason}: {q}")
            continue
        if key in used or key in batch:
            rejected.append(f"tekrar: {q}")
            continue
        batch.add(key)
        result.append({"id": make_id(q, a), "topic": str(item.get("topic", "beyin cimnastiği"))[:60], "question": q, "answer": a, "explanation": e})

    if len(result) < 3:
        raise RuntimeError(f"Groq 3 kaliteli yeni soru üretemedi. Geçerli: {len(result)}. Reddedilenler: {rejected}")
    return result[:3]


def fetch_news_pool(hours_back: int = 20) -> list[dict[str, Any]]:
    history = bot.load_json(bot.HISTORY_FILE, {"processed_news": [], "processed_questions": []})
    now_iso = bot.now_tr().isoformat()
    items: list[dict[str, Any]] = []
    for idx, q in enumerate(generate_questions(history), start=1):
        title = f"Yetişkinlerin yüzde 90'ı bu soruyu çözemiyor: {q['question']}"
        items.append({"title": title, "summary": "Cevap bir sonraki videoda. Daha fazla soru için takip et.", "url": f"quizdenede://{q['id']}", "query": q["topic"], "source": "Groq Brain Teaser", "published_at": now_iso, "fingerprint": q["id"], "viral_score": 100 - idx, "quiz": q})
    return items


def choose_top_three(news: list[dict[str, Any]], history: dict[str, Any]) -> list[dict[str, Any]]:
    used = used_questions(history)
    selected: list[dict[str, Any]] = []
    prev = previous_answer(history)
    for item in news:
        quiz = item.get("quiz", {})
        key = norm(quiz.get("question", ""))
        if key in used:
            continue
        quiz["previous_answer_text"] = prev
        prev = clean_answer(quiz.get("answer", "")) or prev
        selected.append(item)
    if len(selected) < 3:
        raise RuntimeError("Aynı soru tekrar engeli aktif: 3 yeni soru seçilemedi.")
    return selected[:3]


def generate_news_script(item: dict[str, Any]) -> str:
    quiz = item.get("quiz", {})
    q = clean_question(quiz.get("question", item["title"]))
    prev = clean_answer(quiz.get("previous_answer_text", "")) or "İlk video olduğu için önceki cevap yok."
    return f"Yetişkinlerin yüzde 90'ı bu soruyu çözemiyor. {q} Cevap bir sonraki videoda. Daha fazla soru için takip et. Önceki videodaki sorunun cevabı: {prev}"


def build_background_queries(item: dict[str, Any]) -> list[str]:
    topic = str(item.get("query", "")).lower()
    base = ["brain puzzle", "thinking student", "question mark background", "quiz show lights", "logic puzzle", "student exam desk", "education learning"]
    if "kelime" in topic:
        base[:0] = ["letters typography", "word game", "alphabet background"]
    elif "dikkat" in topic:
        base[:0] = ["focus attention", "magnifying glass", "thinking face"]
    elif "mantık" in topic:
        base[:0] = ["logic puzzle", "chess thinking", "brainstorm"]
    return list(dict.fromkeys(base))


def update_history(history: dict[str, Any], selected: list[dict[str, Any]]) -> dict[str, Any]:
    history = _ORIGINAL_UPDATE_HISTORY(history, selected)
    history.setdefault("processed_questions", [])
    for item in selected:
        quiz = item.get("quiz", {})
        if quiz:
            history["processed_questions"].append({"id": quiz.get("id"), "topic": quiz.get("topic"), "question": clean_question(quiz.get("question", "")), "answer": clean_answer(quiz.get("answer", "")), "explanation": quiz.get("explanation"), "used_at": bot.now_tr().isoformat(), "youtube_url": item.get("youtube_url")})
    history["processed_questions"] = history["processed_questions"][-500:]
    return history


def upload_to_youtube(video_path, item, publish_at):
    video_path = str(video_path)
    bot.logger.info("YouTube upload kapalı. Video artifact/release olarak saklanacak: %s", video_path)
    return {"video_id": "youtube_upload_disabled", "youtube_url": f"GitHub Release/Artifact: {video_path}", "publish_at_local": publish_at.isoformat(), "publish_at_utc": publish_at.astimezone(bot.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")}


bot.fetch_news_pool = fetch_news_pool
bot.choose_top_three = choose_top_three
bot.generate_news_script = generate_news_script
bot.build_background_queries = build_background_queries
bot.update_history = update_history
bot.upload_to_youtube = upload_to_youtube
bot.main()

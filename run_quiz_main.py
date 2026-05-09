#!/usr/bin/env python3
"""Quizdenede content wrapper.

Bu dosya main.py'nin video/altyazı/TTS/render sistemine dokunmaz.
Sadece haber kaynağını Groq tabanlı beyin cimnastiği sorularıyla değiştirir
ve Pexels arama kelimelerini quiz konusuna göre ayarlar.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
from datetime import datetime
from typing import Any

import requests

import main as bot

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _qid(question: str, answer: str) -> str:
    return hashlib.sha1(f"{question}|{answer}".encode("utf-8")).hexdigest()


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("Groq JSON döndürmedi")
    return json.loads(text[start : end + 1])


def _recent_questions(history: dict[str, Any], limit: int = 80) -> list[str]:
    questions = []
    for item in history.get("processed_news", [])[-limit:]:
        title = str(item.get("title", ""))
        if title:
            questions.append(title)
    for item in history.get("processed_questions", [])[-limit:]:
        question = str(item.get("question", ""))
        if question:
            questions.append(question)
    return questions[-limit:]


def _fallback_questions() -> list[dict[str, str]]:
    pool = [
        {
            "topic": "dikkat",
            "hook": "Cevabı çok basit ama çoğu kişi yanlış düşünüyor.",
            "question": "Bir yarışta ikinci kişiyi geçersen kaçıncı olursun?",
            "answer": "İkinci olursun.",
            "explanation": "İkinciyi geçince onun sırasını alırsın; birinci olmazsın.",
        },
        {
            "topic": "mantık",
            "hook": "Soru trenle ilgili ama cevap rüzgârda değil.",
            "question": "Elektrikli tren kuzeye gidiyor, rüzgâr batıdan esiyor. Duman hangi yöne gider?",
            "answer": "Hiçbir yöne gitmez.",
            "explanation": "Çünkü elektrikli tren duman çıkarmaz.",
        },
        {
            "topic": "dikkat",
            "hook": "Kelimeyi dikkatli okuyan hemen yakalıyor.",
            "question": "Bir yılda kaç ayda 28 gün vardır?",
            "answer": "12 ayda da vardır.",
            "explanation": "Her ayın içinde en az 28 gün bulunur.",
        },
        {
            "topic": "günlük hayat yanılgısı",
            "hook": "Aynı ağırlığı farklı hayal ettiğin için tuzağa düşebilirsin.",
            "question": "Bir kilo pamuk mu daha ağırdır, bir kilo demir mi?",
            "answer": "İkisi de aynı ağırlıktadır.",
            "explanation": "İkisinin de kütlesi 1 kilogramdır.",
        },
        {
            "topic": "hızlı akıl yürütme",
            "hook": "Soru kolay gibi ama cümleyi kaçırırsan yanılırsın.",
            "question": "Elinde 3 elma var. 2 tanesini alırsan kaç elman olur?",
            "answer": "2 elman olur.",
            "explanation": "Çünkü soru kaç tane aldığını soruyor.",
        },
    ]
    random.shuffle(pool)
    return pool[:3]


def _generate_questions(history: dict[str, Any]) -> list[dict[str, str]]:
    if not GROQ_API_KEY:
        bot.logger.warning("GROQ_API_KEY yok, fallback soru havuzu kullanılıyor.")
        return _fallback_questions()

    avoid = _recent_questions(history)
    prompt = f"""
Türkçe YouTube Shorts için 3 adet BEYİN CİMNASTİĞİ sorusu üret.
Format 'Beyin cimnastiği zamanı' hissinde olsun. 'Bir ortaokullu bile bilir' gibi ifade kullanma.

Kurallar:
- Sorular her çalışmada farklı ve tekrar etmeyen türlerde olsun.
- Matematik ağırlıklı olmasın; en fazla 1 soru küçük hesap içerebilir.
- Türler: dikkat, mantık, kelime oyunu, günlük hayat yanılgısı, unutulan temel bilgi, hızlı akıl yürütme.
- Soru kısa, net, cevap tek ve tartışmasız olsun.
- Tuzaklı olsun ama haksız/uydurma olmasın.
- Çok kolay görünmeli ama düşününce zorlaşmalı.
- Her soru Türkçe olsun.
- Şunlara benzer veya aynı soru üretme: {avoid}

Sadece JSON döndür:
{{
  "questions": [
    {{"topic":"dikkat", "hook":"kısa merak cümlesi", "question":"soru", "answer":"cevap", "explanation":"kısa mantık açıklaması"}}
  ]
}}
""".strip()

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "Sen kısa, net ve yaratıcı Türkçe beyin cimnastiği soruları üreten bir editörsün."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.95,
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        response.raise_for_status()
        data = _extract_json(response.json()["choices"][0]["message"]["content"])
        raw_questions = data.get("questions", [])
    except Exception as exc:
        bot.logger.warning("Groq soru üretimi başarısız, fallback kullanılıyor: %s", exc)
        raw_questions = _fallback_questions()

    cleaned: list[dict[str, str]] = []
    used = set()
    for item in raw_questions:
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        explanation = str(item.get("explanation", "")).strip()
        if not question or not answer or not explanation:
            continue
        qid = _qid(question, answer)
        if qid in used:
            continue
        used.add(qid)
        cleaned.append({
            "id": qid,
            "topic": str(item.get("topic", "beyin cimnastiği")).strip()[:60],
            "hook": str(item.get("hook", "Bu soru düşündüğünden daha zor.")).strip()[:140],
            "question": question[:220],
            "answer": answer[:140],
            "explanation": explanation[:280],
        })

    for item in _fallback_questions():
        if len(cleaned) >= 3:
            break
        item["id"] = _qid(item["question"], item["answer"])
        if item["id"] not in used:
            cleaned.append(item)
    return cleaned[:3]


def _quiz_items_from_questions(questions: list[dict[str, str]]) -> list[dict[str, Any]]:
    now_iso = bot.now_tr().isoformat()
    items: list[dict[str, Any]] = []
    for index, q in enumerate(questions, start=1):
        title = f"Beyin Cimnastiği: {q['question']}"
        summary = f"{q['hook']} Cevap: {q['answer']} Mantık: {q['explanation']}"
        items.append({
            "title": title,
            "summary": summary,
            "url": f"quizdenede://brain-teaser/{q['id']}",
            "query": q["topic"],
            "source": "Groq Brain Teaser",
            "published_at": now_iso,
            "fingerprint": _qid(title, summary),
            "viral_score": 100 - index,
            "quiz": q,
        })
    return items


def fetch_news_pool(hours_back: int = 20) -> list[dict[str, Any]]:
    history = bot.load_json(bot.HISTORY_FILE, {"processed_news": [], "processed_questions": []})
    return _quiz_items_from_questions(_generate_questions(history))


def choose_top_three(news: list[dict[str, Any]], history: dict[str, Any]) -> list[dict[str, Any]]:
    old_fingerprints = {item.get("fingerprint") for item in history.get("processed_news", [])}
    selected = [item for item in news if item.get("fingerprint") not in old_fingerprints]
    if len(selected) < 3:
        selected = news[:3]
    return selected[:3]


def generate_news_script(item: dict[str, Any]) -> str:
    quiz = item.get("quiz", {})
    return (
        "Beyin cimnastiği zamanı. "
        f"{quiz.get('hook', 'Bu soru düşündüğünden daha zor.')} "
        f"Soru geliyor: {quiz.get('question', item['title'])} "
        "Cevabı düşünmek için üç saniyen var. "
        "Üç... İki... Bir... "
        f"Cevap: {quiz.get('answer', '')} "
        f"Mantık şu: {quiz.get('explanation', item.get('summary', ''))} "
        "Sen doğru bildin mi?"
    )


def build_background_queries(item: dict[str, Any]) -> list[str]:
    topic = str(item.get("query", "")).lower()
    base = [
        "brain puzzle",
        "thinking student",
        "question mark background",
        "quiz show lights",
        "school classroom thinking",
        "logic puzzle",
        "student exam desk",
        "education learning",
    ]
    if "kelime" in topic:
        base[:0] = ["letters typography", "word game", "alphabet background"]
    elif "dikkat" in topic:
        base[:0] = ["focus attention", "magnifying glass", "thinking face"]
    elif "günlük" in topic:
        base[:0] = ["daily life thinking", "people thinking", "confused person"]
    elif "mantık" in topic:
        base[:0] = ["logic puzzle", "chess thinking", "brainstorm"]
    return list(dict.fromkeys(base))


def update_history(history: dict[str, Any], selected: list[dict[str, Any]]) -> dict[str, Any]:
    history = bot.update_history(history, selected)
    history.setdefault("processed_questions", [])
    for item in selected:
        quiz = item.get("quiz", {})
        if quiz:
            history["processed_questions"].append({
                "id": quiz.get("id"),
                "topic": quiz.get("topic"),
                "question": quiz.get("question"),
                "answer": quiz.get("answer"),
                "used_at": bot.now_tr().isoformat(),
                "youtube_url": item.get("youtube_url"),
            })
    history["processed_questions"] = history["processed_questions"][-500:]
    return history


def upload_to_youtube(video_path, item, publish_at):
    quiz = item.get("quiz", {})
    item["title"] = "Beyin Cimnastiği: Bu soruyu çözebilir misin? #shorts"
    item["summary"] = f"Soru: {quiz.get('question', '')}\nCevap: {quiz.get('answer', '')}\nMantık: {quiz.get('explanation', '')}"
    return bot.upload_to_youtube(video_path, item, publish_at)


bot.fetch_news_pool = fetch_news_pool
bot.choose_top_three = choose_top_three
bot.generate_news_script = generate_news_script
bot.build_background_queries = build_background_queries
bot.update_history = update_history
bot.upload_to_youtube = upload_to_youtube
bot.main()

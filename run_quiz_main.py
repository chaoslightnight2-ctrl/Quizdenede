#!/usr/bin/env python3
"""Quizdenede wrapper.

main.py render, TTS ve altyazı senkron sistemi aynen kullanılır.
Bu dosya sadece Groq soru üretimini, video metnini ve Pexels arama kelimelerini değiştirir.
Fallback yoktur. Groq yeni ve kaliteli 6 soru üretmezse workflow hata verir.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

os.environ.setdefault("YOUTUBE_REFRESH_TOKEN", "youtube_upload_disabled")

import requests
from groq_client import chat_json
from prompt_contract import CLEAN_OUTPUT_RULES
import main as bot
from quality_gate import spoken_text, tts_text, validate_package, validate_rendered_video, validate_visual_query

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
ENABLE_YOUTUBE_UPLOAD = os.getenv("ENABLE_YOUTUBE_UPLOAD", "0") == "1"
_ORIGINAL_UPDATE_HISTORY = bot.update_history
_ORIGINAL_UPLOAD_TO_YOUTUBE = bot.upload_to_youtube
bot.YOUTUBE_CATEGORY_ID = "27"


def closed_object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


QUIZ_SCHEMA = closed_object({"questions": {"type": "array", "items": closed_object({
    key: {"type": "string"} for key in ("topic", "question", "answer", "explanation", "visual_query")})}})
CHECK_SCHEMA = closed_object({"checks": {"type": "array", "items": closed_object({
    "id": {"type": "string"}, "valid": {"type": "boolean"}, "reason": {"type": "string"}})}})


BAD_QUESTION_PATTERNS = [
    r"bir saatlik yolu\s+1\s+saatte",
    r"hangi kelimenin yazılışında",
    r"hangi kelimede",
    r"kaç tane harf",
    r"hangisinde ['\"]?[a-zçğıöşü]['\"]? harfi yoktur",
    r"ilk iki harfi.*son iki harfi",
    r"ilk harfi.*son harfi",
]

VIRAL_TITLE_TEMPLATES = [
    "Bu sorunun cevabını bulabilir misin?",
    "İlk bakışta kolay; cevabı düşündürüyor.",
    "Bu mantık sorusunda neyi kaçırıyoruz?",
    "Dikkat testi: doğru yanıt hangisi?",
    "Bu bilmeceyi çözmek için dikkatli bak.",
]

VIRAL_TAGS = [
    "shorts",
    "Quizdenede",
    "zeka sorusu",
    "mantık sorusu",
    "dikkat testi",
    "bilmece",
    "genel kültür sorusu",
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
    return text


def clean_answer(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text).strip())
    text = re.sub(r"^(cevap|yanıt)\s*[:\-.]*\s*", "", text, flags=re.I)
    return text.strip()


def viral_title_for_quiz(question: str, topic: str = "zeka") -> str:
    q = clean_question(question).strip()
    if len(q) <= 76:
        return f"{q} #shorts"
    raise ValueError("Soru tamamıyla başlığa sığmalı; Groq daha kısa soru üretmeli")


def viral_description_for_quiz(question: str, answer: str, explanation: str) -> str:
    q = clean_question(question)
    current_answer = clean_answer(answer)
    why = re.sub(r"\s+", " ", explanation).strip()
    lead = "Bu mantık ve dikkat sorusunu çözebilir misin?"
    return (
        f"{lead}\n\nSoru: {q}\n"
        f"Cevap: {current_answer}\nAçıklama: {why}\n\n"
        "İlk tahminini yorumlara yaz.\n\n"
        "Yeni bilmece, dikkat testi ve mantık soruları için Quizdenede'ye abone ol.\n\n"
        "#shorts #ZekaSorusu #MantıkSorusu"
    )



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
    if not answer.strip():
        return False, "cevap çok kısa"
    if len(explanation) < 20:
        return False, "açıklama çok kısa"
    if len(question) > 76 or len(answer) > 140 or len(explanation) > 400:
        return False, "soru veya açıklama kesilmeden kısa ve tamamlanmış olmalı"
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


def verify_questions(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    """Use a separate Groq critic pass; uncertainty rejects instead of falling back."""
    prompt = f"""
Sen katı bir Türkçe quiz doğrulayıcısısın. Aşağıdaki adayları tek tek çöz.
Yalnızca tek ve tartışmasız cevabı olan, bilimsel/tarihsel bilgisi doğru, sorusu eksiksiz,
answer ile explanation alanları birbiriyle uyumlu adaylara valid=true ver.
Kelime oyunu çalışmıyorsa, birden fazla yorum varsa, soru gerekli bilgiyi vermiyorsa,
genel bir bilim olgusunu yanlış genelliyorsa veya emin değilsen valid=false ver.
Konuşma alanlarında kaynak atfı URL noktalama markdown sahne talimatı veya asistan notu varsa valid=false ver.
Metni düzeltme ve yeni soru üretme. Yalnızca JSON döndür:
{{"checks":[{{"id":"...","valid":true,"reason":"kısa gerekçe"}}]}}

Adaylar:
{json.dumps(candidates, ensure_ascii=False)}
""".strip()
    checks = chat_json(prompt, system="Solve each quiz independently and return checks JSON.", temperature=0, max_tokens=1800, schema=CHECK_SCHEMA).get("checks", [])
    for row in checks:
        if row.get("valid") is not True:
            bot.logger.info("Quiz semantic rejection %s: %s", row.get("id"), row.get("reason"))
    valid_ids = {str(row.get("id")) for row in checks if row.get("valid") is True}
    return [candidate for candidate in candidates if candidate["id"] in valid_ids]


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


def recent_list(history: dict[str, Any], limit: int = 30) -> list[str]:
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


def _generate_candidate_round(history: dict[str, Any]) -> list[dict[str, str]]:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY yok. Fallback kapalı; soru üretimi durduruldu.")

    forbidden = recent_list(history)
    feedback = history.get("generation_feedback", [])[-8:]
    prompt = f"""
Quizdenede için dört farklı Türkçe Shorts quiz sorusu üret.
Her sorunun cevabı aynı videoda açıklanır. Tüm JSON alanlarını doldur.
question: 28-76 karakter arası eksiksiz kısa soru. Gerekli bilgi soruda olsun.
İdeal soru 36-60 karakter ve en fazla on iki kelime olsun Uzun oda anahtar lamba kurguları
ve çok koşullu sorular seçme Sayıları yazıya çevirdikten sonra karakter sınırını tekrar kontrol et
Önceki reddedilen soruları kısaltarak tekrar etme Bu kez başka kısa ve net bir soru seç
answer: kısa, tek, kesin cevap. explanation: 20-220 karakter arası doğru gerekçe.
question answer explanation içinde sayıları Türkçe sözcüklerle yaz; site adı kaynakça etiket yazma.
visual_query: ilgili gerçek nesneye yönelik üç ila beş ASCII İngilizce kelime.
Örneğin uzay konusunun görsel sorgusu lunar surface space olabilir; sorgu boş olamaz.
topic: mantık dikkat bilim doğa tarih kültür dil uzamsal düşünme kategorilerinden biri.
Adil ama merak uyandıran soru yaz; açıklaması şaşırtıcı ve anlaşılır olsun.
Seçenek, resim veya ek bilgi olmadan çözülemeyen soru yazma. Belirsiz kelime oyunları,
birden fazla cevabı olan bilmeceler, uydurma bilim ve düz ilkokul hesabı kullanma.
Soruları ve konuları çeşitlendir. Kanıtsız başarı oranı veya abartılı iddia yazma.
Tekrar etme: {json.dumps(forbidden, ensure_ascii=False)}
Önceki üretimde düzeltilmesi gerekenler: {json.dumps(feedback, ensure_ascii=False)}
""".strip()
    raw = chat_json(prompt, system=CLEAN_OUTPUT_RULES + "\nProduce four complete Turkish quizzes matching every schema field. English visual_query is mandatory.",
                    temperature=.55, max_tokens=2400, schema=QUIZ_SCHEMA).get("questions", [])
    diagnostics = Path('output/quiz_generation.jsonl')
    diagnostics.parent.mkdir(parents=True, exist_ok=True)
    with diagnostics.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({"candidates": raw}, ensure_ascii=False) + "\n")

    used = used_questions(history)
    batch: set[str] = set()
    result: list[dict[str, str]] = []
    rejected: list[str] = []
    for item in raw:
        q = clean_question(item.get("question", ""))
        a = clean_answer(item.get("answer", ""))
        e = re.sub(r"\s+", " ", str(item.get("explanation", "")).strip())
        try:
            visual_query = validate_visual_query(str(item.get("visual_query", "")))
        except ValueError as exc:
            rejected.append(f"görsel sorgu {item.get('visual_query', '')!r}: {exc}: {q}")
            continue
        key = norm(q)
        ok, reason = is_good_question(q, a, e)
        if not ok:
            rejected.append(f"{reason}: {q}")
            continue
        if key in used or key in batch:
            rejected.append(f"tekrar: {q}")
            continue
        batch.add(key)
        result.append({"id": make_id(q, a), "topic": str(item.get("topic", "beyin cimnastiği"))[:60], "question": q, "answer": a, "explanation": e, "visual_query": visual_query})

    verified = verify_questions(result) if result else []
    rejected.extend(f"tek ve doğru cevap doğrulanamadı: {q['question']}" for q in result if q not in verified)
    result = verified
    history["generation_feedback"] = rejected[-8:]
    bot.logger.info("Quiz round: %s valid; rejected: %s", len(result), rejected)
    return result



def generate_questions(history):
    import copy
    working = copy.deepcopy(history)
    result = []
    for attempt in range(5):
        try:
            candidates = _generate_candidate_round(working)
        except (ValueError, KeyError, TypeError) as exc:
            bot.logger.warning("Groq quiz round %s/5 invalid: %s", attempt + 1, exc)
            continue
        known = {norm(q["question"]) for q in result}
        for candidate in candidates:
            if norm(candidate["question"]) not in known:
                result.append(candidate)
                known.add(norm(candidate["question"]))
                working.setdefault("processed_questions", []).append(candidate)
        if len(result) >= 6:
            return result[:6]
    raise RuntimeError(f"Same Groq produced only {len(result)}/6 independently verified new quizzes")


def fetch_news_pool(hours_back: int = 20) -> list[dict[str, Any]]:
    history = bot.load_json(bot.HISTORY_FILE, {"processed_news": [], "processed_questions": []})
    now_iso = bot.now_tr().isoformat()
    items: list[dict[str, Any]] = []
    for idx, q in enumerate(generate_questions(history), start=1):
        title = viral_title_for_quiz(q["question"], q["topic"])
        items.append({"title": title, "summary": "Sorunun cevabı ve kısa açıklaması aynı videoda verilir.", "url": f"quizdenede://{q['id']}", "query": q["topic"], "source": "Groq Brain Teaser", "published_at": now_iso, "fingerprint": q["id"], "viral_score": 100 - idx, "quiz": q})
    return items


def choose_six(news: list[dict[str, Any]], history: dict[str, Any]) -> list[dict[str, Any]]:
    used = used_questions(history)
    selected: list[dict[str, Any]] = []
    for item in news:
        quiz = item.get("quiz", {})
        key = norm(quiz.get("question", ""))
        if key in used:
            continue
        selected.append(item)
    if len(selected) < 6:
        raise RuntimeError("Aynı soru tekrar engeli aktif: 6 yeni soru seçilemedi.")
    return selected[:6]


def generate_news_script(item: dict[str, Any]) -> str:
    quiz = item.get("quiz", {})
    q = clean_question(quiz.get("question", item["title"]))
    answer = clean_answer(quiz.get("answer", ""))
    explanation = re.sub(r"\s+", " ", str(quiz.get("explanation", "")).strip())
    hook = "İlk tahminine güveniyor musun"
    narration = f"{q} Cevabını düşünmek için sana üç saniye veriyorum Doğru cevap {answer} Çünkü {explanation}"
    cta = "Yeni ve doğru sorular için Quizdenede kanalına abone ol"
    checked = validate_package(
        title=item.get("title", ""), hook=hook, narration=narration, cta=cta,
        description="Quiz sorusu ve cevabı", channel_name="Quizdenede",
    )
    item["spoken_text"] = checked["spoken_text"]
    item["tts_text"] = tts_text((hook, q, "Cevabını düşünmek için sana üç saniye veriyorum", f"Doğru cevap {answer}", f"Çünkü {explanation}", cta)).replace("Quizdenede", "Küiz dene de")
    return checked["spoken_text"]



def build_background_queries(item: dict[str, Any]) -> list[str]:
    return [validate_visual_query(item.get("quiz", {}).get("visual_query", ""))]


def update_history(history: dict[str, Any], selected: list[dict[str, Any]]) -> dict[str, Any]:
    # Merge the latest disk state so workflow retries cannot overwrite upload receipts.
    history = bot.load_json(bot.HISTORY_FILE, history)
    known_fingerprints = {
        str(row.get("fingerprint", ""))
        for row in history.get("processed_news", [])
        if row.get("fingerprint")
    }
    fresh_items = [
        item for item in selected
        if item.get("fingerprint") and str(item["fingerprint"]) not in known_fingerprints
    ]
    history = _ORIGINAL_UPDATE_HISTORY(history, fresh_items)
    history.setdefault("processed_questions", [])
    known_ids = {row.get("id") for row in history["processed_questions"] if row.get("id")}
    for item in fresh_items:
        quiz = item.get("quiz", {})
        if quiz and quiz.get("id") not in known_ids:
            history["processed_questions"].append({
                "id": quiz.get("id"),
                "topic": quiz.get("topic"),
                "question": clean_question(quiz.get("question", "")),
                "answer": clean_answer(quiz.get("answer", "")),
                "explanation": quiz.get("explanation"),
                "used_at": bot.now_tr().isoformat(),
                "youtube_url": item.get("youtube_url"),
                "video_id": item.get("video_id"),
            })
            known_ids.add(quiz.get("id"))
    history["processed_questions"] = history["processed_questions"][-500:]
    return history


def upload_to_youtube(video_path, item, publish_at):
    quiz = item.get("quiz", {})
    validate_rendered_video(video_path)
    if ENABLE_YOUTUBE_UPLOAD:
        question = clean_question(quiz.get("question", ""))
        item["title"] = viral_title_for_quiz(question, quiz.get("topic", "zeka"))
        item["summary"] = viral_description_for_quiz(question, quiz.get("answer", ""), quiz.get("explanation", ""))
        original_upload = _ORIGINAL_UPLOAD_TO_YOUTUBE
        original_tags = getattr(bot, "YOUTUBE_TAGS", None)
        try:
            category_tags = {
                "bilim": ["bilim sorusu", "bilim ve doğa"],
                "doğa": ["doğa sorusu", "bilim ve doğa"],
                "tarih": ["tarih sorusu", "genel kültür"],
                "dil": ["kelime oyunu", "dil sorusu"],
                "uzamsal": ["uzamsal düşünme", "zeka sorusu"],
                "sayı": ["sayı örüntüsü", "mantık sorusu"],
                "hafıza": ["hafıza testi", "dikkat testi"],
                "günlük": ["günlük hayat sorusu", "mantık sorusu"],
            }
            topic_text = norm(quiz.get("topic", ""))
            specific = next((tags for key, tags in category_tags.items() if key in topic_text), ["zeka sorusu", "mantık sorusu"])
            bot.YOUTUBE_TAGS = list(dict.fromkeys(["Quizdenede", *specific, "dikkat testi", "bilmece", "genel kültür"]))[:7]
            at = publish_at.astimezone(bot.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            body = {"snippet": {"title": item["title"], "description": item["summary"],
                                "tags": bot.YOUTUBE_TAGS, "categoryId": "27"},
                    "status": {"privacyStatus": "private", "publishAt": at, "selfDeclaredMadeForKids": False}}
            request = bot.get_youtube_service().videos().insert(part="snippet,status", body=body,
                media_body=bot.MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024))
            response = None
            while response is None:
                _, response = request.next_chunk(num_retries=3)
            video_id = response.get("id")
            result = {"video_id": video_id, "youtube_url": f"https://youtu.be/{video_id}",
                      "publish_at_local": publish_at.isoformat(), "publish_at_utc": at, "upload_status": "api_insert_confirmed"}
            item["youtube_tags"] = bot.YOUTUBE_TAGS
            if not result.get("video_id") or result.get("video_id") == "youtube_upload_disabled":
                raise RuntimeError("YouTube API yükleme onayı alınamadı; video başarılı yüklenmiş sayılmayacak.")
            bot.logger.info("YouTube videos.insert onayı doğrulandı: %s", result["video_id"])
            item.update(result)
            latest = bot.load_json(bot.HISTORY_FILE, {"processed_news": [], "processed_questions": []})
            bot.save_json(bot.HISTORY_FILE, update_history(latest, [item]))
            return result
        finally:
            if original_tags is not None:
                bot.YOUTUBE_TAGS = original_tags

    video_path = str(video_path)
    bot.logger.info("YouTube upload kapalı. Video artifact/release olarak saklanacak: %s", video_path)
    return {"video_id": "youtube_upload_disabled", "youtube_url": f"GitHub Release/Artifact: {video_path}", "publish_at_local": publish_at.isoformat(), "publish_at_utc": publish_at.astimezone(bot.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")}


bot.fetch_news_pool = fetch_news_pool
bot.choose_top_three = choose_six
bot.generate_news_script = generate_news_script
bot.build_background_queries = build_background_queries
bot.update_history = update_history
bot.upload_to_youtube = upload_to_youtube
from batch_runtime import run as run_batch
if __name__ == "__main__":
    run_batch(bot, quiz=True)

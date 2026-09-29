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
from typing import Any

os.environ.setdefault("YOUTUBE_REFRESH_TOKEN", "youtube_upload_disabled")

import requests
import main as bot
from quality_gate import spoken_text, tts_text, validate_package, validate_rendered_video, validate_visual_query

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
ENABLE_YOUTUBE_UPLOAD = os.getenv("ENABLE_YOUTUBE_UPLOAD", "0") == "1"
_ORIGINAL_UPDATE_HISTORY = bot.update_history
_ORIGINAL_UPLOAD_TO_YOUTUBE = bot.upload_to_youtube
bot.YOUTUBE_CATEGORY_ID = "27"


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
    return text[:220]


def clean_answer(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text).strip())
    text = re.sub(r"^(cevap|yanıt)\s*[:\-.]*\s*", "", text, flags=re.I)
    return text.strip()[:140]


def viral_title_for_quiz(question: str, topic: str = "zeka") -> str:
    q = clean_question(question).strip()
    if len(q) <= 76:
        return f"{q} #shorts"
    clean_topic = re.sub(r"[^A-Za-z0-9çğıöşüÇĞİÖŞÜ ]+", " ", topic).strip() or "Zeka"
    title = f"{clean_topic.title()} sorusunda doğru cevabı bulabilir misin? #shorts"
    if len(title) > 100:
        raise ValueError("Quiz başlığı kesilmeden 100 karaktere sığmıyor")
    return title


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
    answer_tokens = [token for token in an.split() if len(token) >= 3]
    if answer_tokens and not any(token in norm(explanation) for token in answer_tokens):
        return False, "açıklama cevabı doğrulamıyor"
    return True, "ok"


def verify_questions(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    """Use a separate Groq critic pass; uncertainty rejects instead of falling back."""
    prompt = f"""
Sen katı bir Türkçe quiz doğrulayıcısısın. Aşağıdaki adayları tek tek çöz.
Yalnızca tek ve tartışmasız cevabı olan, bilimsel/tarihsel bilgisi doğru, sorusu eksiksiz,
answer ile explanation alanları birbiriyle uyumlu adaylara valid=true ver.
Kelime oyunu çalışmıyorsa, birden fazla yorum varsa, soru gerekli bilgiyi vermiyorsa,
genel bir bilim olgusunu yanlış genelliyorsa veya emin değilsen valid=false ver.
Metni düzeltme ve yeni soru üretme. Yalnızca JSON döndür:
{{"checks":[{{"id":"...","valid":true,"reason":"kısa gerekçe"}}]}}

Adaylar:
{json.dumps(candidates, ensure_ascii=False)}
""".strip()
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "Quiz doğrulayıcısısın. Şüpheli adayı reddet; tahmin yürütme."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_completion_tokens": 1600,
            "reasoning_effort": "low",
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    response.raise_for_status()
    checks = parse_json(response.json()["choices"][0]["message"]["content"]).get("checks", [])
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
Türkçe Quizdenede Shorts için 12 kaliteli, birbirinden farklı beyin cimnastiği ve genel kültür sorusu üret. Sistem bunlardan en iyi 6'sını seçecek.

Kesin format:
- question: sadece sorunun kendisi. Video girişi yazma.
- answer: sadece kısa cevap.
- explanation: cevabın neden doğru olduğunu kısa açıkla.
- visual_query: soruda geçen gerçek nesne veya olayı gösterecek 3-7 İngilizce Pexels arama kelimesi.

En önemli hedef:
- Soru ilk dinleyişte anlaşılmalı, ekranda tek bakışta okunmalı ve izleyici yorum yazmadan önce kendi başına çözmeyi deneyebilmeli.
- Cevap hemen tahmin edilecek kadar bariz olmamalı; zorluk adil olsun ve verilen ipucu gerçekten çözüme götürsün.
- Cevap açıklandığında şaşırtıcı ama tamamen mantıklı ve tatmin edici bir payoff sağlamalı.
- Sorunun ilk cümlesi meydan okuma ve merak uyandırsın; cevabı veya kritik ipucunu videonun başında ele verme.
- Cevap bir sonraki videoda verileceği için soru güçlü bir merak boşluğu oluşturmalı.

Kaynak/tarz:
- Soruları kendin üretmek zorunda değilsin.
- Kendi bilgindeki kaliteli klasik bilmecelerden, internet kültüründeki bilinen mantık/dikkat sorularından veya bunların iyi Türkçe varyasyonlarından yararlanabilirsin.
- Birebir kopya gibi değil; Türkçe, temiz, kısa ve Shorts'a uygun yaz.

Kalite filtresi:
- Klasik tuzak soru olabilir; klasik olması sorun değil.
- Ama çocukça kolay, cevabı bariz, iki doğru cevabı olan veya sınırsız cevabı olan soru üretme.
- 'Hangi kelimede hangi harf yoktur?' gibi belirsiz sorular üretme.
- '1 saatlik yolu 1 saatte giderse kaç saat?' gibi dümdüz hesap üretme.
- Sorunun doğru cevabı tek, net ve tartışmasız olmalı.
- İzleyici cevabı duyunca 'mantıklıymış' demeli, 'bu ne saçma' dememeli.
- En fazla 1 küçük hesap sorusu olabilir.
- 10 aday boyunca türleri geniş ve dengeli dağıt: mantık, dikkat, sözel akıl yürütme, günlük hayat yanılgısı,
  hafıza, sayı/örüntü, bilim/doğa, tarih/kültür, dil ve uzamsal düşünme. Her sorunun topic alanında bu türlerden
  kısa ve anlaşılır bir kategori belirt.
- Adayları izleyiciyi yorumda tahmin yapmaya en çok teşvik edenden başlayarak sırala. Sıralamada şu ölçütleri
  kullan: ilk dinleyişte anlaşılma, ekranda hızlı okunma, tek adil cevap, merak gücü ve kısa açıklamayla tatmin.
  Altı videoya seçilecek adaylar mümkün olduğunca farklı soru türlerinden olsun; aynı cevap veya aynı numarayı kullananları grupla.
  Başlık/soru kancalarını çeşitlendir; “çoğu kişi çözemiyor” gibi kanıtsız oran iddiası kullanma.
- Çok bilinen klasiklerden en fazla 1 tane üret; diğerleri iyi varyasyon veya daha az bilinen klasiklerden olsun.
- Şu soruların aynısını veya çok benzerini ASLA üretme: {forbidden}

Sadece JSON döndür:
{{"questions":[{{"topic":"kaliteli mantık","question":"sadece soru","answer":"kısa cevap","explanation":"kısa açıklama","visual_query":"specific visual search"}}]}}
""".strip()

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "Sen kaliteli Türkçe dikkat, mantık ve klasik bilmece soruları seçen/üreten bir editörsün. Amaç: cevabı merak ettiren, tek cevaplı, adil ve açıklanınca tatmin eden sorular üretmek. Zayıf, çocukça kolay, bariz veya belirsiz soru üretme."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 2400,
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
        try:
            visual_query = validate_visual_query(str(item.get("visual_query", "")))
        except ValueError as exc:
            rejected.append(f"görsel sorgu: {exc}: {q}")
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

    result = verify_questions(result)
    if len(result) < 6:
        raise RuntimeError(f"Groq 6 kaliteli yeni soru üretemedi. Geçerli: {len(result)}. Reddedilenler: {rejected}")
    # Groq returns its candidates strongest-first; choose distinct question types where possible.
    selected: list[dict[str, str]] = []
    seen_topics: set[str] = set()
    for candidate in result:
        topic_key = norm(candidate.get("topic", ""))
        if topic_key and topic_key not in seen_topics:
            selected.append(candidate)
            seen_topics.add(topic_key)
        if len(selected) == 6:
            break
    for candidate in result:
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) == 6:
            break
    return selected[:6]


def fetch_news_pool(hours_back: int = 20) -> list[dict[str, Any]]:
    history = bot.load_json(bot.HISTORY_FILE, {"processed_news": [], "processed_questions": []})
    now_iso = bot.now_tr().isoformat()
    items: list[dict[str, Any]] = []
    for idx, q in enumerate(generate_questions(history), start=1):
        title = viral_title_for_quiz(q["question"], q["topic"])
        items.append({"title": title, "summary": "Cevap bir sonraki videoda. Tahminini yorumlara yaz.", "url": f"quizdenede://{q['id']}", "query": q["topic"], "source": "Groq Brain Teaser", "published_at": now_iso, "fingerprint": q["id"], "viral_score": 100 - idx, "quiz": q})
    return items


def choose_six(news: list[dict[str, Any]], history: dict[str, Any]) -> list[dict[str, Any]]:
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
    if len(selected) < 6:
        raise RuntimeError("Aynı soru tekrar engeli aktif: 6 yeni soru seçilemedi.")
    return selected[:6]


def generate_news_script(item: dict[str, Any]) -> str:
    quiz = item.get("quiz", {})
    q = clean_question(quiz.get("question", item["title"]))
    answer = clean_answer(quiz.get("answer", ""))
    explanation = re.sub(r"\s+", " ", str(quiz.get("explanation", "")).strip())
    hook = "İlk tahminine güveniyor musun"
    narration = f"{q} Cevabını düşünmek için sana üç saniye veriyorum Hazır mısın Doğru cevap {answer} Çünkü {explanation}"
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
            result = original_upload(video_path, item, publish_at)
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
bot.main()

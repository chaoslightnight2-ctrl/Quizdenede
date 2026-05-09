#!/usr/bin/env python3
"""Groq tabanlı Beyin Cimnastiği Shorts botu."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import edge_tts
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.editor import AudioFileClip, ColorClip, CompositeVideoClip, TextClip

load_dotenv()

TZ = ZoneInfo("Europe/Istanbul")
VIDEO_SIZE = (1080, 1920)
OUTPUT_DIR = Path("output")
HISTORY_FILE = Path("news_history.json")
SELECTED_FILE = Path("selected_news.json")
PLAN_FILE = Path("video_plan.json")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
CLIENT_SECRETS_FILE = "client_secrets.json"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "27"

VOICE = os.getenv("VOICE", "tr-TR-AhmetNeural")
VOICE_RATE = os.getenv("VOICE_RATE", "+0%")
VOICE_PITCH = os.getenv("VOICE_PITCH", "-2Hz")
SUBTITLE_FONT = os.getenv("SUBTITLE_FONT", "DejaVu-Sans-Bold")

if not YOUTUBE_REFRESH_TOKEN:
    sys.exit("YOUTUBE_REFRESH_TOKEN tanımlı değil.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("quizdenede")


def now_tr() -> datetime:
    return datetime.now(TZ)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def tr_upper(text: str) -> str:
    table = str.maketrans({"i": "İ", "ı": "I", "ğ": "Ğ", "ü": "Ü", "ş": "Ş", "ö": "Ö", "ç": "Ç"})
    return str(text).translate(table).upper()


def question_id(question: str, answer: str) -> str:
    return hashlib.sha1(f"{question}|{answer}".encode("utf-8")).hexdigest()[:16]


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Groq JSON döndürmedi")
    return json.loads(text[start : end + 1])


def recent_questions(limit: int = 60) -> list[str]:
    history = load_json(HISTORY_FILE, {"processed_questions": []})
    items = history.get("processed_questions", [])[-limit:]
    return [str(item.get("question", "")) for item in items if item.get("question")]


def fallback_questions() -> list[dict[str, str]]:
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
            "topic": "mantık",
            "hook": "Bu soru bilgi değil, dikkat ölçüyor.",
            "question": "Elinde 3 elma var. 2 tanesini alırsan kaç elman olur?",
            "answer": "2 elman olur.",
            "explanation": "Çünkü soru kaç tane aldığını soruyor.",
        },
        {
            "topic": "beyin cimnastiği",
            "hook": "Aynı ağırlığı farklı hayal ettiğin için tuzağa düşebilirsin.",
            "question": "Bir kilo pamuk mu daha ağırdır, bir kilo demir mi?",
            "answer": "İkisi de aynı ağırlıktadır.",
            "explanation": "İkisinin de kütlesi 1 kilogramdır.",
        },
    ]
    random.shuffle(pool)
    return pool[:3]


def generate_questions_with_groq() -> list[dict[str, str]]:
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY yok, fallback soru havuzu kullanılacak.")
        return fallback_questions()

    avoid = recent_questions()
    prompt = f"""
Türkçe YouTube Shorts için 3 adet BEYİN CİMNASTİĞİ sorusu üret.
Format: 'Beyin cimnastiği zamanı' tarzı olacak; 'bir ortaokullu bile bilir' deme.

Kurallar:
- Sorular hep farklı ve tekrar etmeyen türlerde olsun.
- Matematik ağırlıklı olmasın; en fazla 1 soru küçük hesap içerebilir.
- Türler: dikkat, mantık, kelime oyunu, günlük hayat yanılgısı, unutulan temel bilgi, hızlı akıl yürütme.
- Soru kısa, net, cevap tek ve tartışmasız olsun.
- Tuzaklı olsun ama haksız/uydurma olmasın.
- Çok kolay görünmeli ama düşününce zorlaşmalı.
- Her soru Türkçe olsun.
- Şunlara benzer veya aynı soru üretme: {avoid}

Sadece şu JSON formatında dön:
{{
  "questions": [
    {{"topic":"dikkat", "hook":"kısa merak cümlesi", "question":"soru", "answer":"cevap", "explanation":"kısa mantık açıklaması"}}
  ]
}}
""".strip()

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "Sen kısa, net ve yaratıcı Türkçe quiz soruları üreten bir editörsün."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.95,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    data = extract_json(content)
    questions = data.get("questions", [])

    cleaned: list[dict[str, str]] = []
    seen = set()
    for item in questions:
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        explanation = str(item.get("explanation", "")).strip()
        if not question or not answer or not explanation:
            continue
        qid = question_id(question, answer)
        if qid in seen:
            continue
        seen.add(qid)
        cleaned.append({
            "id": qid,
            "topic": str(item.get("topic", "beyin cimnastiği")).strip()[:40],
            "hook": str(item.get("hook", "Bu soru düşündüğünden daha zor.")).strip()[:120],
            "question": question[:220],
            "answer": answer[:120],
            "explanation": explanation[:260],
        })
    if len(cleaned) < 3:
        logger.warning("Groq yeterli temiz soru üretmedi, fallback tamamlıyor.")
        for item in fallback_questions():
            item["id"] = question_id(item["question"], item["answer"])
            if item["id"] not in seen:
                cleaned.append(item)
            if len(cleaned) == 3:
                break
    return cleaned[:3]


def build_script(item: dict[str, str]) -> str:
    return (
        "Beyin cimnastiği zamanı. "
        f"{item['hook']} "
        f"Soru geliyor: {item['question']} "
        "Cevabı düşünmek için üç saniyen var. "
        "Üç... İki... Bir... "
        f"Cevap: {item['answer']} "
        f"Mantık şu: {item['explanation']} "
        "Sen doğru bildin mi?"
    )


async def create_voiceover(script: str, audio_path: Path) -> None:
    talk = edge_tts.Communicate(script, VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH)
    with open(audio_path, "wb") as file:
        async for chunk in talk.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Ses dosyası oluşmadı")


def make_text(text: str, start: float, duration: float, y: int, fontsize: int, color: str = "white", height: int = 260) -> TextClip:
    return (
        TextClip(
            tr_upper(text),
            fontsize=fontsize,
            color=color,
            font=SUBTITLE_FONT,
            stroke_color="black",
            stroke_width=5,
            method="caption",
            size=(940, height),
            align="center",
        )
        .set_start(start)
        .set_duration(duration)
        .set_position(("center", y))
    )


def render_video(item: dict[str, str], audio_path: Path, video_path: Path) -> None:
    audio = AudioFileClip(str(audio_path))
    duration = max(float(audio.duration), 24.0)
    answer_at = min(max(duration * 0.58, 13.0), duration - 7.0)

    bg_color = random.choice([(18, 20, 32), (22, 18, 30), (16, 24, 24), (28, 22, 16)])
    bg = ColorClip(VIDEO_SIZE, color=bg_color, duration=duration).set_audio(audio)
    shade = ColorClip(VIDEO_SIZE, color=(0, 0, 0), duration=duration).set_opacity(0.15)

    clips: list[Any] = [bg, shade]
    clips.append(make_text("BEYİN CİMNASTİĞİ ZAMANI", 0, duration, 90, 58, "yellow", 160))
    clips.append(make_text(item["hook"], 1.2, 4.5, 270, 42, "white", 260))
    clips.append(make_text(item["question"], 4.5, answer_at - 4.5, 500, 58, "white", 560))
    clips.append(make_text("3", answer_at - 3.2, 0.75, 1110, 132, "yellow", 170))
    clips.append(make_text("2", answer_at - 2.2, 0.75, 1110, 132, "yellow", 170))
    clips.append(make_text("1", answer_at - 1.2, 0.75, 1110, 132, "yellow", 170))
    clips.append(make_text(f"CEVAP: {item['answer']}", answer_at, duration - answer_at, 390, 62, "yellow", 280))
    clips.append(make_text(item["explanation"], answer_at + 2.8, max(duration - answer_at - 2.8, 1.5), 750, 44, "white", 440))

    final = CompositeVideoClip(clips, size=VIDEO_SIZE)
    final.write_videofile(str(video_path), codec="libx264", audio_codec="aac", fps=30, preset="medium", threads=4, verbose=False, logger=None)
    audio.close()
    final.close()


def load_client_config() -> dict[str, Any]:
    raw = os.getenv("CLIENT_SECRETS_JSON")
    if raw:
        return json.loads(raw)
    path = Path(CLIENT_SECRETS_FILE)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raise RuntimeError("CLIENT_SECRETS_JSON bulunamadı")


def youtube_service():
    config = load_client_config()
    client_config = config.get("installed") or config.get("web") or next(iter(config.values()))
    credentials = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_config["client_id"],
        client_secret=client_config["client_secret"],
        scopes=YOUTUBE_SCOPES,
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials)


def publish_times() -> list[datetime]:
    result = []
    current = now_tr()
    for hour in (7, 12, 18):
        t = current.replace(hour=hour, minute=0, second=0, microsecond=0)
        if t <= current:
            t += timedelta(days=1)
        result.append(t)
    return result


def upload_video(video_path: Path, item: dict[str, str], publish_at: datetime) -> dict[str, str]:
    title = f"Beyin Cimnastiği: Bu soruyu çözebilir misin? #shorts"
    description = (
        f"Soru: {item['question']}\n"
        f"Cevap: {item['answer']}\n"
        f"Mantık: {item['explanation']}\n\n"
        "#shorts #quiz #zeka #beyincimnastiği #mantık #dikkat"
    )
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": ["shorts", "quiz", "zeka", "beyin cimnastiği", "mantık", "dikkat"],
            "categoryId": YOUTUBE_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024)
    request = youtube_service().videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("YouTube yükleme: %s%%", int(status.progress() * 100))
    video_id = response["id"]
    return {
        "video_id": video_id,
        "youtube_url": f"https://youtu.be/{video_id}",
        "publish_at_local": publish_at.isoformat(),
        "publish_at_utc": body["status"]["publishAt"],
    }


def update_history(items: list[dict[str, str]]) -> None:
    history = load_json(HISTORY_FILE, {"processed_news": [], "processed_questions": []})
    history.setdefault("processed_questions", [])
    for item in items:
        history["processed_questions"].append({
            "id": item["id"],
            "topic": item["topic"],
            "question": item["question"],
            "answer": item["answer"],
            "used_at": now_tr().isoformat(),
            "youtube_url": item.get("youtube_url"),
        })
    history["processed_questions"] = history["processed_questions"][-500:]
    save_json(HISTORY_FILE, history)


def main() -> None:
    logger.info("Quizdenede Groq beyin cimnastiği botu başladı")
    OUTPUT_DIR.mkdir(exist_ok=True)
    items = generate_questions_with_groq()
    times = publish_times()
    plan_rows = []

    save_json(SELECTED_FILE, {"generated_at": now_tr().isoformat(), "format": "Beyin cimnastiği", "selected_quizzes": items})

    for index, item in enumerate(items, start=1):
        logger.info("Video %s soru: %s", index, item["question"])
        item["script"] = build_script(item)
        audio_path = OUTPUT_DIR / f"quiz_voiceover_{index}.mp3"
        video_path = OUTPUT_DIR / f"quiz_short_{index}.mp4"
        asyncio.run(create_voiceover(item["script"], audio_path))
        render_video(item, audio_path, video_path)
        upload_result = upload_video(video_path, item, times[index - 1])
        item.update(upload_result)
        item["scheduled_slot"] = times[index - 1].strftime("%H:%M")
        item["audio_path"] = str(audio_path)
        item["video_path"] = str(video_path)
        plan_rows.append({
            "index": index,
            "topic": item["topic"],
            "question": item["question"],
            "answer": item["answer"],
            "publish_at_local": upload_result["publish_at_local"],
            "youtube_url": upload_result["youtube_url"],
        })

    update_history(items)
    save_json(SELECTED_FILE, {"generated_at": now_tr().isoformat(), "format": "Beyin cimnastiği", "selected_quizzes": items})
    save_json(PLAN_FILE, {"generated_at": now_tr().isoformat(), "videos": plan_rows})
    logger.info("Tamamlandı: %s", PLAN_FILE)


if __name__ == "__main__":
    main()

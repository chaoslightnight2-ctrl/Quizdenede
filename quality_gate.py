"""Fail-closed quality checks shared by the Shorts generation pipeline."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Iterable


SOURCE_MARKERS = (
    "kaynak:", "kaynakça", "kaynaklar:", "haber sitesi", "sitesine göre", "internet sitesi",
    "google news", "www.", "http://", "https://", ".com", ".net", ".org",
)
OUTPUT_MARKERS = (
    "başlık:", "metin:", "senaryo:", "açıklama:", "etiket:", "hashtag:",
    "markdown", "json", "```",
)
GENERIC_VISUALS = {
    "news background", "global news background", "world map news",
    "press conference", "abstract background", "city aerial",
    "question mark background", "thinking student", "education learning",
}


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def spoken_text(text: str) -> str:
    """Return only words and numbers for narration/captions.

    Sentence punctuation is intentionally removed from the persisted spoken text.
    TTS pauses are added separately by :func:`tts_text`.
    """
    value = compact(text)
    value = re.sub(r"%(\d+(?:[.,]\d+)?)", r"yüzde \1", value)
    value = re.sub(r"(?<=\d)[.,](?=\d{3}(?:\D|$))", "", value)
    value = re.sub(r"(?<=\d)[.,](?=\d)", " virgül ", value)
    value = re.sub(r"https?://\S+|www\.\S+", " ", value, flags=re.I)
    value = re.sub(r"[#*_`~<>\[\]{}()|\\/]", " ", value)
    value = re.sub(r"[“”„«»\"'’‘:;,.!?…—–\-]+", " ", value)
    return compact(re.sub(r"[^\w\s]", " ", value))


def tts_text(parts: Iterable[str]) -> str:
    clean = [spoken_text(part) for part in parts if spoken_text(part)]
    return ". ".join(clean) + ("." if clean else "")


def _numbers(text: str) -> set[str]:
    values = re.findall(r"(?<!\w)%?\d+(?:[.,]\d+)*%?(?!\w)", text or "")
    result = set()
    for value in values:
        value = value.strip('%')
        value = re.sub(r'[.,](?=\d{3}(?:[.,]|$))', '', value)
        result.add(value.replace(',', '.'))
    return result


def _cta_key(text: str) -> str:
    value = spoken_text(text).casefold()
    return re.sub(r"\s+", " ", value)


def validate_package(*, title: str, hook: str, narration: str, cta: str,
                     description: str, source_text: str = "",
                     channel_name: str = "", source_names: Iterable[str] = ()) -> dict[str, str]:
    fields = {
        "title": compact(title),
        "hook": compact(hook),
        "narration": compact(narration),
        "cta": compact(cta),
        "description": compact(description),
    }
    missing = [name for name, value in fields.items() if not value]
    if missing:
        raise ValueError("zorunlu alan boş: " + ", ".join(missing))
    if len(fields["title"]) > 90:
        raise ValueError(f"başlık çok uzun: {len(fields['title'])}")
    if re.search(r"\b(?:içi|son iki|ilk iki|aya|kırmız)\?", fields["title"], re.I):
        raise ValueError("başlık kelime veya cümle ortasında kesilmiş")

    combined_raw = " ".join((fields["hook"], fields["narration"], fields["cta"]))
    low = combined_raw.casefold()
    forbidden = [marker for marker in (*SOURCE_MARKERS, *OUTPUT_MARKERS) if marker in low]
    if forbidden:
        raise ValueError("konuşma metninde yasak kaynak/çıktı kalıntısı: " + ", ".join(forbidden))
    leaked_names = [compact(name) for name in source_names if len(compact(name)) >= 3 and compact(name).casefold() in low]
    if leaked_names:
        raise ValueError("konuşma metninde yayıncı/site adı var: " + ", ".join(leaked_names))
    if re.search(r"(^|\s)[#@][\wçğıöşü]+", combined_raw, re.I):
        raise ValueError("konuşma metninde hashtag veya kullanıcı etiketi var")

    spoken = spoken_text(combined_raw)
    words = spoken.split()
    if len(words) < 28 or len(words) > 100:
        raise ValueError(f"konuşma metni kelime sayısı uygunsuz: {len(words)}")
    if len(set(word.casefold() for word in words)) < max(12, int(len(words) * 0.45)):
        raise ValueError("konuşma metninde aşırı tekrar var")

    cta_key = _cta_key(fields["cta"])
    if len(re.findall(r"\babone ol\b", _cta_key(combined_raw))) != 1:
        raise ValueError("abonelik çağrısı tam bir kez geçmeli")
    if re.search(r"\babone ol\b", _cta_key(fields["hook"] + " " + fields["narration"])):
        raise ValueError("CTA yalnızca cta alanında bulunmalı")
    if cta_key and _cta_key(combined_raw).count(cta_key) != 1:
        raise ValueError("abonelik çağrısı tekrar ediyor")
    if channel_name and spoken_text(channel_name).casefold() not in spoken_text(fields["cta"]).casefold():
        raise ValueError(f"CTA kanal adını içermiyor: {channel_name}")

    source_numbers = _numbers(source_text)
    generated_numbers = _numbers(combined_raw + " " + fields["title"] + " " + fields["description"])
    unsupported = sorted(generated_numbers - source_numbers)
    if source_text and unsupported:
        raise ValueError("kaynakta olmayan sayı kullanıldı: " + ", ".join(unsupported))

    return {
        **fields,
        "spoken_text": spoken,
        "tts_text": tts_text((fields["hook"], fields["narration"], fields["cta"])),
    }


def validate_visual_query(query: str) -> str:
    value = compact(query).lower()
    # Harmless surrounding punctuation is formatting, not another query/model.
    value = re.sub(r"[\"'’‘“”,.:;!?_/-]+", " ", value)
    value = compact(value)
    words = re.findall(r"[a-z0-9]+", value)
    if not 2 <= len(words) <= 7:
        raise ValueError("visual_query 2-7 İngilizce kelime olmalı")
    if value in GENERIC_VISUALS:
        raise ValueError("visual_query konuya özel değil")
    if re.search(r"[^a-z0-9\s-]", value):
        raise ValueError("visual_query yalnızca İngilizce arama kelimeleri içermeli")
    return value


def caption_chunks(word_ts, min_words: int = 2, max_words: int = 4,
                   max_duration: float = 1.35, max_gap: float = 0.45):
    """Create readable 2-4 word captions directly from Edge TTS boundaries."""
    words = []
    for start, duration, word in word_ts or []:
        clean = spoken_text(word)
        if clean:
            words.append((float(start), max(float(duration), 0.08), clean))
    if not words:
        raise ValueError("altyazı için kelime zaman damgası yok")

    canonical = []
    index = 0
    while index < len(words):
        triplet = [row[2].casefold() for row in words[index:index + 3]]
        if triplet == ["küiz", "dene", "de"]:
            first, last = words[index], words[index + 2]
            canonical.append((first[0], last[0] + last[1] - first[0], "Quizdenede"))
            index += 3
            continue
        if triplet == ["türkiye", "den", "haber"]:
            first, last = words[index], words[index + 2]
            canonical.append((first[0], last[0] + last[1] - first[0], "Türkiye’den Haber"))
            index += 3
            continue
        canonical.append(words[index])
        index += 1
    words = canonical

    chunks = []
    current = []
    start = end = 0.0
    for word_start, duration, word in words:
        word_end = word_start + duration
        gap = word_start - end if current else 0.0
        projected = word_end - start if current else duration
        display_words = sum(len(part.split()) for part in current) + len(word.split())
        if current and (display_words > max_words or projected > max_duration or gap > max_gap):
            chunks.append((start, max(end - start, 0.01), " ".join(current)))
            current = []
        if not current:
            start = word_start
        current.append(word)
        end = word_end
    if current:
        chunks.append((start, max(end - start, 0.01), " ".join(current)))

    # Keep every word at its actual boundary; never move text without its timestamp.
    return chunks


def validate_caption_timing(chunks, audio_duration: float) -> None:
    if not chunks:
        raise ValueError("altyazı parçaları boş")
    previous_end = -0.01
    for start, duration, text in chunks:
        if start < previous_end - 0.05:
            raise ValueError("altyazı zamanları çakışıyor")
        if duration <= 0 or not 1 <= len(text.split()) <= 4:
            raise ValueError("altyazı parçası okunabilir değil")
        previous_end = start + duration
    if chunks[0][0] > 1.25:
        raise ValueError("ilk altyazı sesten fazla geç başlıyor")
    if previous_end > audio_duration + 0.35:
        raise ValueError("altyazı ses süresini aşıyor")


def validate_rendered_video(path: str | Path) -> None:
    video = Path(path)
    if not video.exists() or video.stat().st_size < 250_000:
        raise ValueError("render edilmiş video yok veya bozuk")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    )
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(info.get("format", {}).get("duration") or 0)
    if not video_stream or not audio_stream:
        raise ValueError("final videoda görüntü veya ses akışı eksik")
    if int(video_stream.get("height") or 0) <= int(video_stream.get("width") or 0):
        raise ValueError("final video dikey değil")
    if not 18 <= duration <= 65:
        raise ValueError(f"final video süresi uygunsuz: {duration:.1f} saniye")


def validate_full_narration(video_path, audio_path):
    path = Path(audio_path).with_suffix('.words.json')
    if not path.exists():
        raise ValueError("Sesin gerçek kelime zamanları bulunamadı")
    rows = json.loads(path.read_text(encoding='utf-8'))['words']
    end = max(start + duration for start, duration, word in rows)
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,duration', '-of', 'json', str(video_path)],
                            check=True, capture_output=True, text=True)
    streams = json.loads(result.stdout)['streams']
    for stream in streams:
        if stream.get('codec_type') in ('video', 'audio') and float(stream.get('duration', 0)) + .15 < end:
            raise ValueError("Son konuşma kelimeleri final videoda kesiliyor")

from __future__ import annotations

import os

import main as bot

CAPTION_TIME_SHIFT = float(os.getenv("CAPTION_TIME_SHIFT", "0.00"))
CAPTION_MAX_WORDS = int(os.getenv("CAPTION_MAX_WORDS", "2"))
CAPTION_MAX_SPAN = float(os.getenv("CAPTION_MAX_SPAN", "0.95"))
CAPTION_MIN_DURATION = float(os.getenv("CAPTION_MIN_DURATION", "0.16"))
CAPTION_GAP_CUTOFF = float(os.getenv("CAPTION_GAP_CUTOFF", "0.38"))


def _shift_time(value: float) -> float:
    return max(0.0, float(value) + CAPTION_TIME_SHIFT)


def chunk_timestamps_voice_synced(word_ts):
    if not word_ts:
        return []

    words = []
    for start, duration, word in word_ts:
        text = bot.clean_caption_word(word)
        if not text:
            continue
        start = _shift_time(start)
        duration = max(float(duration), 0.05)
        end = start + duration
        words.append((start, end, text))

    if not words:
        return []

    captions = []
    current = []
    chunk_start = words[0][0]
    previous_end = words[0][1]

    for start, end, text in words:
        gap = start - previous_end
        projected_span = end - chunk_start
        should_flush = bool(current) and (
            len(current) >= CAPTION_MAX_WORDS
            or projected_span > CAPTION_MAX_SPAN
            or gap > CAPTION_GAP_CUTOFF
        )
        if should_flush:
            captions.append((chunk_start, max(previous_end - chunk_start, CAPTION_MIN_DURATION), " ".join(current)))
            current = [text]
            chunk_start = start
        else:
            current.append(text)
        previous_end = end

    if current:
        captions.append((chunk_start, max(previous_end - chunk_start, CAPTION_MIN_DURATION), " ".join(current)))

    fixed = []
    for index, (start, duration, text) in enumerate(captions):
        end = start + duration
        if index + 1 < len(captions):
            next_start = captions[index + 1][0]
            end = min(end, next_start - 0.02)
        if end <= start:
            end = start + CAPTION_MIN_DURATION
        fixed.append((start, end - start, text))

    return fixed


bot.chunk_timestamps = chunk_timestamps_voice_synced

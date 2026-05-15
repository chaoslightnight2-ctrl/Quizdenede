from __future__ import annotations

import os

import main as bot

CAPTION_TIME_SHIFT = float(os.getenv("CAPTION_TIME_SHIFT", "0.00"))
CAPTION_MIN_DURATION = float(os.getenv("CAPTION_MIN_DURATION", "0.05"))
CAPTION_END_PAD = float(os.getenv("CAPTION_END_PAD", "0.00"))
CAPTION_NEXT_GAP = float(os.getenv("CAPTION_NEXT_GAP", "0.015"))


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
        duration = max(float(duration), CAPTION_MIN_DURATION)
        words.append((start, start + duration, text))

    captions = []
    for index, (start, end, text) in enumerate(words):
        end = end + CAPTION_END_PAD
        if index + 1 < len(words):
            next_start = words[index + 1][0]
            end = min(end, next_start - CAPTION_NEXT_GAP)
        if end <= start:
            end = start + CAPTION_MIN_DURATION
        captions.append((start, end - start, text))

    return captions


bot.chunk_timestamps = chunk_timestamps_voice_synced

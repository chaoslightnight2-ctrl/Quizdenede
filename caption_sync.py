from __future__ import annotations

import main as bot


def chunk_timestamps_word_boundary(word_ts):
    if not word_ts:
        return []

    captions = []
    cleaned = []
    for start, duration, word in word_ts:
        text = bot.clean_caption_word(word)
        if not text:
            continue
        cleaned.append((float(start), max(float(duration), 0.04), text))

    for index, (start, duration, text) in enumerate(cleaned):
        end = start + duration
        if index + 1 < len(cleaned):
            next_start = cleaned[index + 1][0]
            end = min(end, next_start - 0.01)
        if end <= start:
            end = start + 0.04
        captions.append((start, end - start, text))

    return captions


bot.chunk_timestamps = chunk_timestamps_word_boundary

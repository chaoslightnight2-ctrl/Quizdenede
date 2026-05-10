from __future__ import annotations

import main as bot

_original_chunk_timestamps = bot.chunk_timestamps


def chunk_timestamps_exact_voice(word_ts):
    chunks = _original_chunk_timestamps(word_ts)
    if not chunks:
        return chunks

    fixed = []
    for start, duration, text in chunks:
        fixed.append((start, max(duration, 0.08), text))

    return fixed


bot.chunk_timestamps = chunk_timestamps_exact_voice

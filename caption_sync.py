from __future__ import annotations

import os
import main as bot

_original_chunk_timestamps = bot.chunk_timestamps
_caption_pause_hold = float(os.getenv("CAPTION_PAUSE_HOLD", "0.65"))
_final_caption_hold = float(os.getenv("FINAL_CAPTION_HOLD", "0.35"))


def chunk_timestamps_with_pause_hold(word_ts):
    chunks = _original_chunk_timestamps(word_ts)
    if not chunks:
        return chunks

    fixed = []
    for index, (start, duration, text) in enumerate(chunks):
        spoken_end = start + duration
        end = spoken_end

        if index + 1 < len(chunks):
            next_start = chunks[index + 1][0]
            pause_end = min(next_start - 0.015, spoken_end + _caption_pause_hold)
            end = max(spoken_end, pause_end)
        else:
            end = spoken_end + _final_caption_hold

        fixed.append((start, max(end - start, 0.12), text))

    return fixed


bot.chunk_timestamps = chunk_timestamps_with_pause_hold

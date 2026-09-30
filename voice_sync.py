"""Captions must follow the exact TTS stream, never estimated timestamps."""
from __future__ import annotations

import asyncio
import html
import re
import subprocess
import edge_tts
from quality_gate import spoken_text


def validate_words(script, boundaries):
    expected = spoken_text(html.unescape(script)).casefold().split()
    received = spoken_text(' '.join(html.unescape(row[2]) for row in boundaries)).casefold().split()
    # Edge may render numeric abbreviations differently. Require the prompt to
    # spell them out rather than silently distributing different caption words.
    if received != expected:
        raise ValueError("TTS word boundaries differ from narration; subtitles stopped")


def quiz_pause(audio_path, rows):
    marker = 'sana üç saniye veriyorum'.split()
    tokens = [spoken_text(row[2]).casefold() for row in rows]
    index = next((i + len(marker) - 1 for i in range(len(tokens)) if tokens[i:i + len(marker)] == marker), None)
    if index is None:
        return rows
    cut = rows[index][0] + rows[index][1]
    raw = audio_path.with_suffix('.unpaused.mp3')
    audio_path.replace(raw)
    filters = (f'[0:a]asplit=2[a][b];[a]atrim=end={cut},asetpts=PTS-STARTPTS[first];'
               f'[b]atrim=start={cut},asetpts=PTS-STARTPTS[last];'
               'anullsrc=r=24000:cl=mono,atrim=duration=3[silence];'
               '[first][silence][last]concat=n=3:v=0:a=1[out]')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-filter_complex', filters,
                    '-map', '[out]', '-c:a', 'libmp3lame', str(audio_path)], check=True)
    return [(start + (3 if i > index else 0), duration, word) for i, (start, duration, word) in enumerate(rows)]


async def synthesize(script, audio_path, bot):
    error = None
    for attempt in range(3):
        rows = []
        try:
            stream = edge_tts.Communicate(script, bot.DEFAULT_VOICE, rate=bot.RATE, pitch=bot.PITCH, boundary="WordBoundary")
            with open(audio_path, "wb") as output:
                async for part in stream.stream():
                    if part['type'] == 'audio':
                        output.write(part['data'])
                    elif part['type'] == 'WordBoundary':
                        rows.append((part['offset'] / 10_000_000, part['duration'] / 10_000_000, html.unescape(part['text'])))
            if not audio_path.exists() or audio_path.stat().st_size == 0 or not rows:
                raise ValueError("TTS audio or word boundaries missing")
            validate_words(script, rows)
            return quiz_pause(audio_path, rows)
        except Exception as exc:
            error = exc
            if attempt < 2:
                await asyncio.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Same voice failed after 3 attempts: {error}")

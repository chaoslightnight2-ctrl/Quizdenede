"""Render-time checks for Quizdenede."""
from __future__ import annotations

import main as bot
from quality_gate import caption_chunks, validate_caption_timing, validate_rendered_video

_original_voiceover = bot.create_voiceover
_original_build = bot.build_video_for_item


async def create_voiceover(script, audio_path):
    from voice_sync import synthesize
    word_ts = await synthesize(script, audio_path, bot)
    audio = bot.AudioFileClip(str(audio_path))
    try:
        validate_caption_timing(caption_chunks(word_ts), float(audio.duration))
    finally:
        audio.close()
    return word_ts


def build_video_for_item(item, index):
    spoken = item.get("script", "")
    tts = item.get("tts_text", "")
    if not spoken or not tts:
        raise ValueError("temiz Quiz konuşma metni veya TTS metni yok")
    item["script"] = tts
    try:
        result = _original_build(item, index)
    finally:
        item["script"] = spoken
    validate_rendered_video(result["video_path"])
    return result


bot.create_voiceover = create_voiceover
bot.chunk_timestamps = caption_chunks
bot.build_video_for_item = build_video_for_item

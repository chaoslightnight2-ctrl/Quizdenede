import asyncio
import os
import runpy
from pathlib import Path

import edge_tts

VOICE = os.getenv("VOICE", "tr-TR-AhmetNeural")
RATE = os.getenv("VOICE_RATE", "+18%")
PITCH = os.getenv("VOICE_PITCH", "-4Hz")
OUT = Path("edge_tts_healthcheck.mp3")


def apply_copied_patches() -> None:
    patch_files = [
        "patch_tts.py",
        "patch_subtitles_denede.py",
        "patch_pause_sync.py",
        "patch_turkish_subtitle_chars.py",
        "patch_direct_news_hook.py",
    ]
    for patch_file in patch_files:
        path = Path(patch_file)
        if not path.exists():
            print(f"Skipping missing patch: {patch_file}")
            continue
        print(f"Applying copied patch: {patch_file}")
        runpy.run_path(str(path), run_name="__main__")


async def main() -> None:
    print(f"Edge TTS healthcheck voice={VOICE} rate={RATE} pitch={PITCH}")
    print(f"edge_tts module={edge_tts.__file__}")
    # The live service can accept a turn and close before any audio.
    # Spread bounded retries across time; keep the same provider and exact voice.
    for attempt in range(5):
        try:
            # New stream and empty file on every attempt; never retain partial audio.
            communicate = edge_tts.Communicate(
                "Bu kısa bir erkek ses testi.", VOICE, rate=RATE, pitch=PITCH,
                boundary="WordBoundary")
            word_count = 0
            with OUT.open("wb") as audio:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        word_count += 1
            if not OUT.exists() or OUT.stat().st_size == 0:
                raise RuntimeError("Edge TTS healthcheck empty audio")
            if word_count == 0:
                raise RuntimeError("Edge TTS healthcheck missing real word timings")
            print(f"Edge TTS OK bytes={OUT.stat().st_size} word_boundaries={word_count}")
            break
        except Exception as error:
            OUT.unlink(missing_ok=True)
            if attempt == 4:
                raise
            print(f"Edge TTS same-voice retry {attempt + 1}/4: {type(error).__name__}")
            await asyncio.sleep((15, 30, 60, 120)[attempt])
    apply_copied_patches()

if __name__ == "__main__":
    asyncio.run(main())

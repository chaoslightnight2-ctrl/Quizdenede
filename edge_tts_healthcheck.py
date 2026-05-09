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
    if OUT.exists():
        OUT.unlink()
    print(f"Edge TTS healthcheck voice={VOICE} rate={RATE} pitch={PITCH}")
    print(f"edge_tts module={edge_tts.__file__}")
    communicate = edge_tts.Communicate(
        "Bu kısa bir erkek ses testi.",
        VOICE,
        rate=RATE,
        pitch=PITCH,
    )
    word_count = 0
    with open(OUT, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_count += 1
    if not OUT.exists() or OUT.stat().st_size == 0:
        raise RuntimeError("Edge TTS healthcheck empty audio")
    print(f"Edge TTS OK bytes={OUT.stat().st_size} word_boundaries={word_count}")
    apply_copied_patches()


if __name__ == "__main__":
    asyncio.run(main())

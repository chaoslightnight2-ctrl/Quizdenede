from __future__ import annotations

import main as bot
from quality_gate import caption_chunks


# Edge TTS word boundaries are already voice-synchronous. Group them into
# readable phrases without adding a time shift or stretching across pauses.
bot.chunk_timestamps = caption_chunks

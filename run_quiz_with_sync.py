#!/usr/bin/env python3
from __future__ import annotations

import caption_sync  # noqa: F401
import background_diversity  # noqa: F401
import groq_quality_guard  # noqa: F401
import quiz_quality_runtime  # noqa: F401
import run_quiz_main  # noqa: F401

from batch_runtime import run
if __name__ == "__main__":
    run(run_quiz_main.bot, quiz=True)

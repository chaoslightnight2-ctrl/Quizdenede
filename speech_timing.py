"""Keep caption starts out of measured long silences without stretching words."""
import os
import re
import subprocess


def align_caption_starts(audio_path, rows):
    result = subprocess.run([os.getenv('FFMPEG_BINARY', 'ffmpeg'), '-hide_banner', '-i', str(audio_path),
        '-af', 'silencedetect=noise=-50dB:d=0.35', '-f', 'null', '-'],
        check=True, capture_output=True, text=True)
    gaps = []
    start = None
    for line in result.stderr.splitlines():
        match = re.search(r'silence_start: ([0-9.]+)', line)
        if match:
            start = float(match.group(1))
        match = re.search(r'silence_end: ([0-9.]+)', line)
        if match and start is not None:
            gaps.append((start, float(match.group(1))))
            start = None
    aligned = []
    for word_start, duration, word in rows:
        end = word_start + duration
        for quiet_start, quiet_end in gaps:
            # WordBoundary can start a grouped caption inside its preceding
            # silence. Trim only that label's silent lead; preserve its end
            # and all underlying word boundaries rather than shifting the sentence.
            if quiet_start <= word_start < quiet_end and .10 < quiet_end - word_start <= .55 and quiet_end < end - .05:
                word_start = quiet_end
                break
        aligned.append((word_start, end - word_start, word))
    return aligned

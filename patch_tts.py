from pathlib import Path

p = Path("main.py")
s = p.read_text(encoding="utf-8")

s = s.replace('RATE = os.getenv("VOICE_RATE", "+8%")', 'RATE = os.getenv("VOICE_RATE", "+0%")')
s = s.replace('RATE = os.getenv("VOICE_RATE", "+15%")', 'RATE = os.getenv("VOICE_RATE", "+0%")')
s = s.replace('RATE = os.getenv("VOICE_RATE", "+18%")', 'RATE = os.getenv("VOICE_RATE", "+0%")')
s = s.replace('PITCH = os.getenv("VOICE_PITCH", "-3Hz")', 'PITCH = os.getenv("VOICE_PITCH", "-2Hz")')
s = s.replace('PITCH = os.getenv("VOICE_PITCH", "-5Hz")', 'PITCH = os.getenv("VOICE_PITCH", "-2Hz")')
s = s.replace('PITCH = os.getenv("VOICE_PITCH", "-4Hz")', 'PITCH = os.getenv("VOICE_PITCH", "-2Hz")')

p.write_text(s, encoding="utf-8")
print("Edge TTS normal speed patch applied")

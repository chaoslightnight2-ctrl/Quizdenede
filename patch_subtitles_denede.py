from pathlib import Path

p = Path("main.py")
s = p.read_text(encoding="utf-8")

if "from moviepy.config import change_settings" not in s:
    s = s.replace("from moviepy.editor import", "from moviepy.config import change_settings\nfrom moviepy.editor import")
if "SUBTITLE_FONT = os.getenv" not in s:
    marker = "logger = logging.getLogger"
    idx = s.find(marker)
    if idx != -1:
        s = s[:idx] + "change_settings({\"IMAGEMAGICK_BINARY\": os.getenv(\"IMAGEMAGICK_BINARY\", \"/usr/bin/convert\")})\nSUBTITLE_FONT = os.getenv(\"SUBTITLE_FONT\", \"DejaVu-Sans-Bold\")\n" + s[idx:]

s = s.replace("MAX_CAPTION_WORDS = 3", "MAX_CAPTION_WORDS = 2")
s = s.replace("MAX_CAPTION_DURATION = 0.75", "MAX_CAPTION_DURATION = 0.68")
s = s.replace("FONT_SIZE = 58", "FONT_SIZE = 64")
s = s.replace("STROKE_WIDTH = 4", "STROKE_WIDTH = 6")
s = s.replace("font=font,", "font=SUBTITLE_FONT,")
s = s.replace("method=\"caption\" if len(text) > 12 else \"label\",", "method=\"caption\",")
s = s.replace("size=(VIDEO_SIZE[0] - 180, None),", "size=(VIDEO_SIZE[0] - 140, 210),")

p.write_text(s, encoding="utf-8")
print("Haberdenede subtitle settings applied")

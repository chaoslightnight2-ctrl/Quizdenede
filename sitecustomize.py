import os


def _tr_upper(text):
    table = str.maketrans({
        "i": "İ",
        "ı": "I",
        "ğ": "Ğ",
        "ü": "Ü",
        "ş": "Ş",
        "ö": "Ö",
        "ç": "Ç",
    })
    return str(text).translate(table).upper()


try:
    import moviepy.editor as editor

    _OriginalTextClip = editor.TextClip

    def HaberdenedeTextClip(txt, *args, **kwargs):
        kwargs["fontsize"] = int(os.getenv("SUBTITLE_FONT_SIZE", "64"))
        kwargs["color"] = os.getenv("SUBTITLE_COLOR", "white")
        kwargs["font"] = os.getenv("SUBTITLE_FONT", "DejaVu-Sans-Bold")
        kwargs["stroke_color"] = os.getenv("SUBTITLE_STROKE_COLOR", "black")
        kwargs["stroke_width"] = int(os.getenv("SUBTITLE_STROKE_WIDTH", "6"))
        kwargs["method"] = "caption"
        kwargs["size"] = (940, 210)
        kwargs["align"] = "center"
        return _OriginalTextClip(_tr_upper(txt), *args, **kwargs)

    editor.TextClip = HaberdenedeTextClip
except Exception as exc:
    print(f"sitecustomize TextClip patch skipped: {exc}")

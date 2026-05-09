# Haberdenede YouTube Shorts Bot

Bu repo `denede` reposundaki YouTube Shorts bot kodunun video/media dosyalari olmadan kopyalanmis halidir.

## Icerik

- `main.py`: Shorts senaryosu uretir, TTS seslendirme yapar, Pexels'ten arka plan video alir, altyazi ekler ve YouTube'a yukler.
- `requirements.txt`: Python bagimliliklari.
- `.github/workflows/run-bot.yml`: GitHub Actions ile manuel/zamanli calistirma.
- `.gitignore`: MP4/MP3 ve gizli dosyalari repoya dahil etmez.

## Gerekli GitHub Secrets

Repo Settings > Secrets and variables > Actions bolumune sunlari ekle:

```text
PEXELS_API_KEY
YOUTUBE_REFRESH_TOKEN
CLIENT_SECRETS_JSON
```

`CLIENT_SECRETS_JSON`, Google Cloud OAuth client JSON icerigidir.

## Lokal kurulum

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
python main.py
```

## Not

Bot calisinca `final_shorts.mp4`, `voiceover.mp3`, `background_video.mp4` gibi runtime dosyalari uretir. Bunlar bilerek Git'e eklenmez.

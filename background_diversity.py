from __future__ import annotations

import random

import requests
import main as bot

_used_background_urls: set[str] = set()
_rng = random.SystemRandom()


def search_pexels_video_diverse(query: str) -> str | None:
    headers = {"Authorization": bot.PEXELS_API_KEY}
    try:
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "per_page": 20, "orientation": "portrait", "size": "large"},
            timeout=20,
        )
        response.raise_for_status()

        candidates: list[tuple[int, str]] = []
        for video in response.json().get("videos", []):
            for vf in video.get("video_files", []):
                width = int(vf.get("width") or 0)
                height = int(vf.get("height") or 0)
                link = vf.get("link")
                if not link or width <= 0 or height <= 0:
                    continue
                if height < width:
                    continue
                score = width * height
                candidates.append((score, link))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        top_links = []
        seen = set()
        for _, link in candidates:
            if link in seen:
                continue
            seen.add(link)
            top_links.append(link)
            if len(top_links) >= 8:
                break

        fresh = [link for link in top_links if link not in _used_background_urls]
        pool = fresh or top_links
        chosen = _rng.choice(pool)
        _used_background_urls.add(chosen)
        return chosen
    except Exception as exc:
        bot.logger.warning("Pexels arka plan hatası (%s): %s", query, exc)
        return None


bot.search_pexels_video = search_pexels_video_diverse

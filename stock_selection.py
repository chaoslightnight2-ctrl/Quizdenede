"""Match actual descriptions before choosing portrait resolution."""
import json
from pathlib import Path
import requests
import main as bot
from stock_relevance import select_assets

_cache = {}

def search_pexels_video(query):
    context = getattr(bot, '_visual_context', '')
    key = (query, context)
    if key in _cache:
        return _cache[key]
    response = requests.get('https://api.pexels.com/videos/search',
        headers={'Authorization': bot.PEXELS_API_KEY},
        params={'query': query, 'per_page': 20, 'orientation': 'portrait', 'size': 'large'}, timeout=30)
    response.raise_for_status()
    assets = []
    for asset in response.json().get('videos', []):
        files = [f for f in asset.get('video_files', []) if f.get('link')
                 and int(f.get('width') or 0) > 0 and int(f.get('height') or 0) >= int(f['width'])]
        if files:
            assets.append({**asset, 'eligible_files': files})
    chosen = select_assets([{'query': query, 'text': context, 'assets': assets}])[0]
    file = max(chosen['eligible_files'], key=lambda f: int(f['width']) * int(f['height']))
    record = {'query': query, 'narration': context, 'asset': {k: chosen.get(k) for k in ('id', 'url', 'title', 'description')}, 'file': file['link']}
    path = Path('output/stock-selections.jsonl')
    path.parent.mkdir(exist_ok=True)
    with path.open('a', encoding='utf-8') as out:
        out.write(json.dumps(record, ensure_ascii=False) + '\n')
    bot.logger.info('Matched stock asset: %s', chosen.get('url'))
    _cache[key] = file['link']
    return file['link']

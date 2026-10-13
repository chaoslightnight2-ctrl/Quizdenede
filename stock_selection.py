"""Match actual descriptions before choosing portrait resolution."""
import json
from pathlib import Path
import requests
import main as bot
from stock_plan import select_with_query_repair

_cache = {}

def search_pexels_video(query):
    context = getattr(bot, '_visual_context', '')
    key = (query, context)
    if key in _cache:
        return _cache[key]
    def fetch(search_query):
        response = requests.get('https://api.pexels.com/videos/search',
            headers={'Authorization': bot.PEXELS_API_KEY},
            params={'query': search_query, 'per_page': 20, 'size': 'large'}, timeout=30)
        response.raise_for_status()
        assets = []
        for asset in response.json().get('videos', []):
            files = [f for f in asset.get('video_files', []) if f.get('link')
                     and int(f.get('width') or 0) > 0 and int(f.get('height') or 0) > 0]
            if files:
                assets.append({**asset, 'eligible_files': files})
        return assets
    selected, used_queries = select_with_query_repair(
        [{'query': query, 'text': context}], fetch)
    chosen = selected[0]
    file = max(chosen['eligible_files'], key=lambda f: int(f['width']) * int(f['height']))
    record = {'original_query': query, 'query': used_queries[0], 'narration': context, 'asset': {k: chosen.get(k) for k in ('id', 'url', 'title', 'description')}, 'file': file['link']}
    path = Path('output/stock-selections.jsonl')
    path.parent.mkdir(exist_ok=True)
    with path.open('a', encoding='utf-8') as out:
        out.write(json.dumps(record, ensure_ascii=False) + '\n')
    bot.logger.info('Matched stock asset: %s', chosen.get('url'))
    _cache[key] = file['link']
    return file['link']

"""Live reference input for genuine Groq writing; never supplies canned narration."""
from functools import lru_cache
import re
import requests

@lru_cache(maxsize=1)
def fetch_sources():
    response = requests.get('https://en.wikipedia.org/w/api.php', params={
        'action': 'query', 'generator': 'random', 'grnnamespace': 0, 'grnlimit': 20,
        'prop': 'extracts|info', 'exintro': 1, 'explaintext': 1, 'inprop': 'url',
        'format': 'json', 'formatversion': 2,
    }, headers={'User-Agent': 'ShortsReferenceReader/1.0 (educational factual context)'}, timeout=45)
    response.raise_for_status()
    rows = []
    for page in response.json().get('query', {}).get('pages', []):
        text = re.sub(r'\s+', ' ', page.get('extract', '')).strip()
        if len(text.split()) < 90 or 'may refer to:' in text:
            continue
        rows.append({'id': str(page['pageid']), 'title': page['title'],
                     'url': page['fullurl'], 'text': text[:2600]})
        if len(rows) == 6:
            break
    if len(rows) < 4:
        raise RuntimeError('Live reference pool insufficient; no unsourced or substitute script used')
    return rows

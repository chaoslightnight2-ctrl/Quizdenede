"""Live audience-directed reference searches; no canned narration or random articles."""
from functools import lru_cache
from datetime import datetime, timezone
import re
import time
from email.utils import parsedate_to_datetime
import requests

DOMAINS = {
    'daily': ('domestic technology', 'food science', 'sleep', 'weather', 'material', 'sense'),
    'behavior': ('memory', 'perception', 'attention', 'learning', 'human behavior', 'social psychology'),
    'science': ('human body', 'animal', 'solar system', 'electricity', 'water', 'plant'),
    'technology': ('mobile phone', 'internet', 'computer', 'battery', 'artificial intelligence', 'transport'),
    'quiz': ('human body', 'solar system', 'animal', 'geography', 'material', 'science'),
}
_page_cycles = {}
_last_request = 0

def search_query(term):
    return f'intitle:"{term}" -intitle:film -intitle:album -intitle:song -intitle:novel -intitle:television -intitle:fiction -intitle:list -intitle:timeline -intitle:classification -articletopic:biography -articletopic:films -articletopic:television -articletopic:music'

def request_page(params):
    global _last_request
    for attempt in range(3):
        time.sleep(max(0, 2 - (time.monotonic() - _last_request)))
        response = requests.get('https://en.wikipedia.org/w/api.php', params=params,
            headers={'User-Agent': 'ShortsReferenceReader/1.0 (educational factual context)'}, timeout=45)
        _last_request = time.monotonic()
        if response.status_code in (429, 502, 503, 504) and attempt < 2:
            value = response.headers.get('Retry-After', '')
            try:
                delay = float(value)
            except ValueError:
                try:
                    delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
                except (ValueError, TypeError):
                    delay = 5 * 2 ** attempt
            time.sleep(max(0, delay))
            continue
        response.raise_for_status()
        return response

def search_terms(focus):
    value = focus.casefold()
    key = ('quiz' if not focus else 'behavior' if 'davran' in value or 'psikoloji' in value
           else 'technology' if 'teknoloji' in value else 'science' if 'bilim' in value else 'daily')
    terms = DOMAINS[key]
    offset = datetime.now(timezone.utc).toordinal() % len(terms)
    return terms[offset:] + terms[:offset]

@lru_cache(maxsize=8)
def fetch_sources(focus=''):
    cycle = _page_cycles.get(focus, 0)
    rows, seen = [], set()
    for term in search_terms(focus):
        response = request_page({
            'action': 'query', 'generator': 'search', 'gsrsearch': search_query(term),
            'gsrnamespace': 0, 'gsrlimit': 3, 'gsroffset': cycle * 3,
            'prop': 'extracts|info', 'exintro': 1, 'explaintext': 1, 'exlimit': 3,
            'inprop': 'url', 'format': 'json', 'formatversion': 2,
        })
        pages = response.json().get('query', {}).get('pages', [])
        pages.sort(key=lambda page: (page.get('title', '').casefold() != term.casefold(), len(page.get('title', '').split()), page.get('index', 999)))
        for page in pages:
            text = re.sub(r'\s+', ' ', page.get('extract', '')).strip()
            if len(text.split()) < 90 or 'may refer to:' in text or page['pageid'] in seen:
                continue
            seen.add(page['pageid'])
            selected = []
            for sentence in re.split(r'(?<=[.!?])\s+', text):
                if selected and len(' '.join(selected)) + len(sentence) > 1700:
                    break
                selected.append(sentence)
            rows.append({'id': str(page['pageid']), 'title': page['title'], 'url': page['fullurl'], 'text': ' '.join(selected)})
            if len(rows) == 6:
                _page_cycles[focus] = cycle + 1
                return rows
    if len(rows) < 4:
        raise RuntimeError('Live audience reference pool insufficient; no substitute script used')
    _page_cycles[focus] = cycle + 1
    return rows

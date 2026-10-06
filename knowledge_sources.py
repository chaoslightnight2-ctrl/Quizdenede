"""Live audience-directed reference searches; no canned narration or random articles."""
from functools import lru_cache
from datetime import datetime, timezone
import re
import requests

DOMAINS = {
    'daily': ('household technology', 'food science', 'sleep biology', 'weather science', 'everyday materials', 'human senses'),
    'behavior': ('human memory', 'human perception', 'attention psychology', 'learning psychology', 'human behaviour', 'social psychology'),
    'science': ('human body', 'animal biology', 'solar system', 'electricity science', 'water properties', 'plant biology'),
    'technology': ('mobile phone technology', 'internet technology', 'computer technology', 'battery technology', 'artificial intelligence', 'transport technology'),
    'quiz': ('human body', 'solar system', 'animal biology', 'geography earth', 'everyday materials', 'general science'),
}
_page_cycle = 0

def search_terms(focus):
    value = focus.casefold()
    key = ('quiz' if not focus else 'behavior' if 'davran' in value or 'psikoloji' in value
           else 'technology' if 'teknoloji' in value else 'science' if 'bilim' in value else 'daily')
    terms = DOMAINS[key]
    offset = datetime.now(timezone.utc).toordinal() % len(terms)
    return terms[offset:] + terms[:offset]

@lru_cache(maxsize=8)
def fetch_sources(focus=''):
    global _page_cycle
    cycle = _page_cycle
    _page_cycle += 1
    rows, seen = [], set()
    for term in search_terms(focus):
        response = requests.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'generator': 'search', 'gsrsearch': term,
            'gsrnamespace': 0, 'gsrlimit': 3, 'gsroffset': cycle * 3,
            'prop': 'extracts|info', 'exintro': 1, 'explaintext': 1, 'exlimit': 3,
            'inprop': 'url', 'format': 'json', 'formatversion': 2,
        }, headers={'User-Agent': 'ShortsReferenceReader/1.0 (educational factual context)'}, timeout=45)
        response.raise_for_status()
        pages = response.json().get('query', {}).get('pages', [])
        pages.sort(key=lambda page: page.get('index', 999))
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
                return rows
    if len(rows) < 4:
        raise RuntimeError('Live audience reference pool insufficient; no substitute script used')
    return rows

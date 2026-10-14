"""Rank actual Pexels metadata locally; never call an LLM for clips."""
import re
from urllib.parse import unquote, urlsplit

IGNORED = {'video', 'videos', 'footage', 'vertical', 'portrait', 'background',
           'scene', 'scenes', 'close', 'up', 'shot', 'view', 'showing', 'with', 'the', 'and'}
ALIASES = {'laboratory': 'lab', 'laboratories': 'lab', 'scientist': 'researcher',
           'scientists': 'researcher', 'microscopic': 'microscope', 'military': 'army'}


def tokens(value):
    return {ALIASES.get(w, w[:-1] if len(w) > 4 and w.endswith('s') else w)
            for w in re.findall(r'[a-z]+', str(value).lower()) if w not in IGNORED}


def asset_description(asset):
    # The numeric CDN filename says nothing about the content. Use the actual
    # Pexels page slug and its description fields, never the user's search text.
    path = unquote(urlsplit(str(asset.get('url', ''))).path)
    return ' '.join([path, *[str(asset.get(k, '')) for k in ('title', 'description', 'alt', 'tags')]])


def relevance(query, asset):
    # A raw stock mockup is unfinished footage, even when its device matches.
    description = re.sub(r'[-_]+', ' ', asset_description(asset)).casefold()
    if re.search(r'\b(?:green|blue)\s+screen\b|\bchrom[ae]\s*key\b|\b(?:blank|empty)\s+(?:screen|display)\b|\b(?:screen|display)\s+mockup\b', description):
        return 0.0
    wanted = tokens(query)
    return len(wanted & tokens(asset_description(asset))) / max(1, len(wanted))


def select_assets(scenes):
    """Return the best described candidate for each original query, without API tokens."""
    selected = []
    for index, scene in enumerate(scenes):
        ranked = [(relevance(scene['query'], asset), asset)
                  for asset in scene['assets']]
        eligible = [(score, asset) for score, asset in ranked if score > 0]
        if not eligible:
            raise ValueError(f'No described asset matches scene {index}: {scene["query"]}')
        # max preserves search order on ties; no invented asset or random substitute.
        selected.append(max(eligible, key=lambda row: row[0])[1])
    return selected

"""Keep named astronomy subjects from being replaced by a different body."""
import re


def matches_named_subject(query, video):
    words = set(re.findall(r'[a-z]+', query.lower()))
    named = words.intersection({'jupiter', 'saturn', 'mars', 'mercury', 'venus', 'neptune', 'uranus'})
    if not named:
        return True
    # Pexels OR-style search can return Moon footage for 'jupiter planet'.
    # Use the actual asset description URL rather than trusting the search query.
    asset_words = set(re.findall(r'[a-z]+', str(video.get('url', '')).lower()))
    return bool(named.intersection(asset_words))

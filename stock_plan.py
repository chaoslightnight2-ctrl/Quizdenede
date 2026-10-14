"""Fetch original clip queries once and select locally, without Groq repair calls."""
if __package__:
    from .stock_relevance import select_assets
else:
    from stock_relevance import select_assets


def select_with_query_repair(scenes, fetch):
    # Keep the existing caller API; query repair no longer spends model tokens.
    offered = [{**scene, 'assets': fetch(scene['query'])} for scene in scenes]
    return select_assets(offered), [scene['query'] for scene in scenes]

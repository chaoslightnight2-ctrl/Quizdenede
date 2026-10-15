"""Verify public YouTube delivery. Upload receipts and private tests are not input."""
from datetime import datetime, time, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
import requests

CHANNELS = {'Haberdenede': 'UCGaV2Xk_1mFavFlCkdUOgAQ', 'Globalhaberdenede': 'UCxRqfXR2BmK-TBHh77SlTEw',
            'Quizdenede': 'UCMVToyerFF_UxUP0k_2GAPQ', 'denede': 'UCU-N6tFV2_YVElMaB0YXPrQ'}
TZ = ZoneInfo('Europe/Istanbul')
NS = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}


def inspect_feed(xml, now, hours):
    now = now.astimezone(TZ)
    document = ET.fromstring(xml)
    rows = {}
    for entry in document.findall('a:entry', NS):
        video_id = entry.findtext('yt:videoId', namespaces=NS)
        published = entry.findtext('a:published', namespaces=NS)
        if not video_id or not published:
            continue
        at = datetime.fromisoformat(published.replace('Z', '+00:00')).astimezone(TZ)
        rows[video_id] = {'video_id': video_id, 'title': entry.findtext('a:title', namespaces=NS),
                          'published_at_local': at.isoformat(), 'url': f'https://youtu.be/{video_id}'}
    ordered = sorted(rows.values(), key=lambda row: row['published_at_local'], reverse=True)
    today = [row for row in ordered if datetime.fromisoformat(row['published_at_local']).date() == now.date()]
    due = [hour for hour in hours if datetime.combine(now.date(), time(hour), TZ) + timedelta(minutes=20) <= now]
    return {'checked_at': now.isoformat(), 'source': 'youtube_public_feed',
            'latest_public': ordered[0] if ordered else None, 'public_today': today,
            'public_count_today': len(today), 'minimum_publications_due': len(due),
            'due_hours': due, 'public_delivery_verified': len(today) >= len(due)}


def main():
    repo = os.environ['GITHUB_REPOSITORY'].rsplit('/', 1)[-1]
    root = Path(__file__).resolve().parents[1]
    if (root / 'freefaceless').is_dir():
        sys.path.insert(0, str(root / 'freefaceless'))
        schedule = importlib.import_module('src.publish_schedule')
    else:
        sys.path.insert(0, str(root))
        schedule = importlib.import_module('publish_schedule')
    response = requests.get('https://www.youtube.com/feeds/videos.xml', params={'channel_id': CHANNELS[repo]}, timeout=30)
    response.raise_for_status()
    report = inspect_feed(response.content, datetime.now(timezone.utc), schedule.publication_hours(int(os.getenv('DAILY_VIDEO_COUNT', '3'))))
    report.update(repo=repo, channel_id=CHANNELS[repo], run_id=os.getenv('GITHUB_RUN_ID'))
    (root / 'maintenance/public-delivery.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report['public_delivery_verified']:
        raise SystemExit(f"PUBLIC DELIVERY UNCONFIRMED: {report['public_count_today']}/{report['minimum_publications_due']} due publications visible on YouTube")


if __name__ == '__main__':
    main()

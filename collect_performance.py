"""Read real owner analytics. Missing metrics stay missing; never infer swipe rate."""
import argparse
import csv
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import requests
try:
    from .audience_strategy import category
    from .performance_feedback import learn, number
except ImportError:
    from audience_strategy import category
    from performance_feedback import learn, number

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'src':
    ROOT = ROOT.parent

def history_video_id(row):
    if row.get('video_id'):
        return row['video_id']
    # Older confirmed uploads store the returned YouTube URL, not a separate ID.
    url = row.get('youtube_url')
    if not isinstance(url, str):
        return None
    parts = urlparse(url)
    if parts.scheme not in ('https', 'http'):
        return None
    video = None
    if parts.netloc in ('youtu.be', 'www.youtu.be'):
        video = parts.path.removeprefix('/')
    elif parts.netloc in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if parts.path == '/watch':
            video = next(iter(parse_qs(parts.query).get('v', [])), None)
        elif parts.path.startswith('/shorts/'):
            video = parts.path.removeprefix('/shorts/')
    return video if video and re.fullmatch(r'[A-Za-z0-9_-]{11}', video) else None

def history_rows():
    path = ROOT / ('state.json' if (ROOT / 'src').exists() else 'news_history.json')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        rows = data.get('published', data.get('processed_news', []))
        return [{**row, 'video_id': history_video_id(row)} for row in rows if isinstance(row, dict)]
    except (OSError, ValueError):
        return []

def published(row):
    return row.get('publish_at_local') or row.get('publish_at_utc') or row.get('publish_at')

def metadata(row):
    return {'video_id': row['video_id'], 'published_at': published(row),
            'audience_bucket': row.get('audience_bucket') or category(row.get('topic', '') + ' ' + row.get('title', '')),
            'hook_style': row.get('hook_style', '')}

def table(response):
    headers = [h['name'] for h in response.get('columnHeaders', [])]
    rows = response.get('rows', [])
    if any(len(row) != len(headers) for row in rows):
        raise ValueError('Analytics response columns do not match rows')
    return [dict(zip(headers, row)) for row in rows]

class AnalyticsUnavailable(RuntimeError):
    pass

def read_api(records, now):
    analytics_refresh = os.getenv('YOUTUBE_ANALYTICS_REFRESH_TOKEN')
    analytics_client = os.getenv('YOUTUBE_ANALYTICS_CLIENT_SECRETS_JSON')
    if analytics_client and not analytics_refresh:
        raise AnalyticsUnavailable('analytics_refresh_missing')
    refresh = analytics_refresh or os.getenv('YOUTUBE_REFRESH_TOKEN')
    config_text = analytics_client or os.getenv('CLIENT_SECRETS_JSON')
    if not refresh or not config_text:
        raise AnalyticsUnavailable('credentials_missing')
    config = json.loads(config_text)
    client = config.get('installed') or config.get('web')
    if not isinstance(client, dict) or not client.get('client_id') or not client.get('client_secret'):
        raise AnalyticsUnavailable('oauth_client_config_missing')
    response = requests.post('https://oauth2.googleapis.com/token', data={
        'grant_type': 'refresh_token', 'refresh_token': refresh,
        'client_id': client['client_id'], 'client_secret': client['client_secret']}, timeout=30)
    if not response.ok:
        raise AnalyticsUnavailable('oauth_refresh_unavailable_' + str(response.status_code))
    token = response.json()['access_token']
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + token
    dates = {'ids': 'channel==MINE', 'startDate': (now.date() - timedelta(days=28)).isoformat(),
             'endDate': (now.date() - timedelta(days=3)).isoformat()}
    def query(**params):
        result = session.get('https://youtubeanalytics.googleapis.com/v2/reports', params={**dates, **params}, timeout=30)
        if not result.ok:
            body = result.json() if 'json' in result.headers.get('content-type', '') else {}
            reason = next(iter(body.get('error', {}).get('errors', [])), {}).get('reason', 'http_error')
            reason = re.sub(r'[^a-zA-Z0-9_]', '', reason)
            raise AnalyticsUnavailable(f'analytics_{result.status_code}_{reason}')
        return table(result.json())
    stats = query(dimensions='video', metrics='views,engagedViews,averageViewDuration,averageViewPercentage',
                  sort='-views', maxResults=200)
    known = {r['video_id']: metadata(r) for r in records if r.get('video_id')}
    output = []
    for stat in stats:
        video = stat['video']
        if video in known:
            output.append({**known[video], **stat, 'stayed_to_watch_pct': None})
    for row in output[:6]:
        if (number(row.get('engagedViews')) or 0) < 100:
            continue
        try:
            points = query(dimensions='elapsedVideoTimeRatio', metrics='audienceWatchRatio', filters='video==' + row['video_id'])
            points.sort(key=lambda p: p['elapsedVideoTimeRatio'])
            row['retention'] = points
            changes = [(b['elapsedVideoTimeRatio'], a['audienceWatchRatio'] - b['audienceWatchRatio'])
                       for a, b in zip(points, points[1:])]
            if changes:
                at, drop = max(changes, key=lambda p: p[1])
                row['largest_drop_at_video_fraction'] = at
                row['largest_drop_ratio'] = drop
        except AnalyticsUnavailable as exc:
            row['retention_status'] = str(exc)
    return output

STUDIO_COLUMNS = {
    'video_id': ('video_id', 'Video', 'İçerik', 'Content'),
    'views': ('views', 'Görüntüleme', 'Views'),
    'engagedViews': ('engagedViews', 'Aktif izlenme', 'Engaged views'),
    'averageViewDuration': ('averageViewDuration', 'Ortalama görüntüleme süresi', 'Average view duration'),
    'averageViewPercentage': ('averageViewPercentage', 'Ortalama görüntüleme yüzdesi (%)', 'Average percentage viewed (%)'),
    'stayed_to_watch_pct': ('stayed_to_watch_pct', 'İzlemeye devam edenler (%)', 'Stayed to watch (%)'),
}

def studio_value(row, key):
    for column in STUDIO_COLUMNS[key]:
        if column in row:
            return row[column]
    return None

def studio_duration(value):
    """Studio exports h:mm:ss; normalized CSV continues to accept seconds."""
    if value is None or ':' not in str(value):
        return number(value)
    text = str(value).strip()
    if not re.fullmatch(r'(?:\d+:)?\d{1,2}:\d{2}', text):
        return None
    parts = [int(part) for part in text.split(':')]
    if any(part >= 60 for part in parts[-2:]):
        return None
    return float(sum(part * 60 ** index for index, part in enumerate(reversed(parts))))

def read_studio_csv(path, records):
    known = {r['video_id']: metadata(r) for r in records if r.get('video_id')}
    output = []
    with open(path, encoding='utf-8-sig', newline='') as stream:
        for stat in csv.DictReader(stream):
            stat = {key.strip(): value for key, value in stat.items() if key is not None}
            video = (studio_value(stat, 'video_id') or '').strip()
            if video not in known:
                continue
            metrics = {key: number(studio_value(stat, key)) for key in
                ('views', 'engagedViews', 'averageViewPercentage', 'stayed_to_watch_pct')}
            metrics['averageViewDuration'] = studio_duration(studio_value(stat, 'averageViewDuration'))
            output.append({**known[video], **metrics})
    if not output:
        raise ValueError('CSV needs video_id, Video, İçerik or Content and matching uploaded video IDs; see PERFORMANCE.md')
    return output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--studio-csv')
    parser.add_argument('--require-access', action='store_true')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    report = {'generated_at': now.isoformat(), 'status': 'unavailable', 'videos': [], 'learning': {},
              'stayed_to_watch_status': 'Studio export required; not computed from engagedViews/views'}
    try:
        records = history_rows()
        report['videos'] = read_studio_csv(args.studio_csv, records) if args.studio_csv else read_api(records, now)
        report['status'] = 'ok'
        report['source'] = 'studio_csv' if args.studio_csv else 'youtube_analytics_api'
        report['learning'] = learn(report['videos'], now)
    except (AnalyticsUnavailable, requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
        report['reason'] = str(exc) if isinstance(exc, AnalyticsUnavailable) else type(exc).__name__
    target = ROOT / 'performance/analytics.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report.get(key) for key in ('status', 'reason', 'source')}, ensure_ascii=True))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(f"\nAudience analytics: {report['status']} {report.get('reason', '')}; {len(report['videos'])} matched videos.\n")
    if args.require_access and report['status'] != 'ok':
        raise SystemExit(2)

if __name__ == '__main__':
    main()

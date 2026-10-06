"""Audit existing insert receipts and render artifacts; never call videos.insert."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import requests

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def youtube_service():
    config = json.loads(os.environ['CLIENT_SECRETS_JSON'])
    config = config.get('installed') or config.get('web')
    creds = Credentials(token=None, refresh_token=os.environ['YOUTUBE_REFRESH_TOKEN'],
        token_uri='https://oauth2.googleapis.com/token', client_id=config['client_id'], client_secret=config['client_secret'])
    creds.refresh(Request())
    return build('youtube', 'v3', credentials=creds)


def inspect_media(path):
    data = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    video = next(s for s in data['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
    duration = float(data['format']['duration'])
    if video['width'] >= video['height'] or not 10 <= duration <= 65:
        raise ValueError('Rendered media is not a complete portrait Short')
    if float(video.get('duration', duration)) + .25 < float(audio.get('duration', duration)):
        raise ValueError('Video ends before the audio track')
    return {'duration': duration, 'width': video['width'], 'height': video['height'], 'audio_codec': audio['codec_name']}


CHANNELS = {
    'Haberdenede': 'UCGaV2Xk_1mFavFlCkdUOgAQ',
    'Globalhaberdenede': 'UCxRqfXR2BmK-TBHh77SlTEw',
    'Quizdenede': 'UCMVToyerFF_UxUP0k_2GAPQ',
    'denede': 'UCU-N6tFV2_YVElMaB0YXPrQ',
}

def public_listing():
    repo = os.getenv('GITHUB_REPOSITORY', '').rsplit('/', 1)[-1]
    channel = CHANNELS.get(repo)
    if not channel:
        return {}
    response = requests.get('https://www.youtube.com/feeds/videos.xml', params={'channel_id': channel}, timeout=25)
    response.raise_for_status()
    document = ET.fromstring(response.content)
    ns = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
    return {entry.findtext('yt:videoId', namespaces=ns): {
                'title': entry.findtext('a:title', namespaces=ns),
                'published': entry.findtext('a:published', namespaces=ns)}
            for entry in document.findall('a:entry', ns)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact-dir', default='audit-artifacts')
    parser.add_argument('--source-run', required=True)
    args = parser.parse_args()
    root = Path(args.artifact_dir)
    result = {'source_run': args.source_run, 'verified_at': datetime.now(timezone.utc).isoformat(),
              'videos': [], 'errors': [], 'accepted_count': 0, 'processed_count': 0, 'complete': False}
    reports = list(root.rglob('run_report.json'))
    manifests = list(root.rglob('daily_manifest.json'))
    rows = []
    target_count = 3
    if reports:
        data = json.loads(reports[0].read_text(encoding='utf-8'))
        if str(data.get('run_id')) != args.source_run:
            result['errors'].append('Artifact report belongs to another run')
        else:
            rows = data.get('videos', [])
            target_count = int(data.get('target_count', 6))
            result['generation_errors'] = data.get('errors', [])
    elif manifests:
        manifest_rows = json.loads(manifests[0].read_text(encoding='utf-8'))
        rows = [row for row in manifest_rows if str(row.get('run_id')) == args.source_run]
        if len(rows) != len(manifest_rows):
            result['errors'].append('Older manifest receipts are not proof of uploads in this run')
        target_count = len(rows) if rows else 3
    else:
        result['errors'].append('No upload receipt report in source artifacts')
    try:
        service = youtube_service()
    except Exception as exc:
        service = None
        result['errors'].append(f'OAuth refresh could not verify processing: {type(exc).__name__}')
    try:
        listed = public_listing()
    except Exception as exc:
        listed = {}
        result['public_listing_error'] = type(exc).__name__
    for position, source in enumerate(rows, 1):
        index = int(source.get('index', position))
        vid = source.get('video_id')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(vid)):
            result['errors'].append({'index': index, 'error': source.get('error', 'No actual insert ID')})
            continue
        row = {'index': index, 'video_id': vid, 'youtube_url': f'https://youtu.be/{vid}',
               'title': source.get('title'), 'narration': source.get('narration'),
               'publish_at': source.get('publish_at_utc') or source.get('publish_at') or source.get('scheduled_publish_at_utc'),
               'upload_status': 'api_insert_confirmed'}
        if service:
            try:
                data = service.videos().list(part='status,processingDetails,snippet', id=vid).execute(num_retries=3)
                items = data.get('items', [])
                if items:
                    actual = items[0]
                    status = actual.get('status', {})
                    processing = actual.get('processingDetails', {}).get('processingStatus')
                    row.update(youtube_status=status, processing_status=processing, title=actual['snippet']['title'])
                    if status.get('uploadStatus') in ('rejected', 'failed', 'deleted') or processing in ('failed', 'terminated'):
                        row['upload_status'] = 'youtube_rejected'
                    elif status.get('uploadStatus') == 'processed' or processing == 'succeeded':
                        row['upload_status'] = 'youtube_processed'
                    else:
                        row['processing_status'] = processing or 'pending'
                else:
                    row['verification_error'] = 'Private video not visible with existing OAuth grant'
            except HttpError as exc:
                if exc.resp.status == 403 and b'insufficientPermissions' in exc.content:
                    row['processing_status'] = 'readback_scope_unavailable'
                else:
                    row['verification_error'] = f'YouTube readback HTTP {exc.resp.status}'
        row['publication_status'] = 'public_listed' if vid in listed else 'not_verified'
        if vid in listed:
            row['public_listing'] = listed[vid]
        elif row.get('publish_at'):
            try:
                at = datetime.fromisoformat(row['publish_at'].replace('Z', '+00:00'))
                if at > datetime.now(timezone.utc):
                    row['publication_status'] = 'scheduled_wait'
            except ValueError:
                pass
        media = list(root.rglob(f'short_{index}.mp4')) if reports else list(root.rglob('final.mp4'))
        if not reports:
            folder = Path(source.get('path', '')).parent.name
            media = [p for p in media if p.parent.name == folder]
        if media:
            try:
                row['media_check'] = inspect_media(media[0])
                frames = Path('maintenance/previews')
                frames.mkdir(parents=True, exist_ok=True)
                subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(media[0]),
                    '-vf', 'fps=1/6,scale=216:384,tile=6x1', '-frames:v', '1', str(frames / f'{vid}.jpg')], check=True)
                row['preview'] = f'maintenance/previews/{vid}.jpg'
            except Exception as exc:
                row['media_error'] = str(exc)
        result['videos'].append(row)
        print(f"{index}: {row['upload_status']} {row['youtube_url']}")
    result['accepted_count'] = sum(row['upload_status'] in ('api_insert_confirmed', 'youtube_processed') for row in result['videos'])
    result['processed_count'] = sum(row['upload_status'] == 'youtube_processed' for row in result['videos'])
    result['target_count'] = target_count
    result['published_count'] = sum(row['publication_status'] == 'public_listed' for row in result['videos'])
    result['accepted_complete'] = result['accepted_count'] == target_count and all('media_check' in row and 'media_error' not in row for row in result['videos'])
    result['complete'] = result['accepted_complete'] and result['published_count'] == target_count
    Path('maintenance').mkdir(exist_ok=True)
    Path('maintenance/latest-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with open(os.environ.get('GITHUB_STEP_SUMMARY', os.devnull), 'a', encoding='utf-8') as summary:
        summary.write(f"YouTube accepted: {result['accepted_count']}/{target_count}; processing verified: {result['processed_count']}/{target_count}; publicly listed: {result['published_count']}/{target_count}\n\n")
        for row in result['videos']:
            summary.write(f"- [{row['title']}]({row['youtube_url']}): {row['upload_status']}\n")
    if not result['accepted_complete']:
        raise SystemExit(f'{target_count} accepted complete videos are not yet verified; see maintenance/latest-verification.json')


if __name__ == '__main__':
    main()

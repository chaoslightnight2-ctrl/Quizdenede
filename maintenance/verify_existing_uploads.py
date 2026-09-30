"""Audit existing insert receipts and render artifacts; never call videos.insert."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

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
    if reports:
        data = json.loads(reports[0].read_text(encoding='utf-8'))
        if str(data.get('run_id')) != args.source_run:
            result['errors'].append('Artifact report belongs to another run')
        else:
            rows = data.get('videos', [])
            result['generation_errors'] = data.get('errors', [])
    elif manifests:
        rows = json.loads(manifests[0].read_text(encoding='utf-8'))
    else:
        result['errors'].append('No upload receipt report in source artifacts')
    try:
        service = youtube_service()
    except Exception as exc:
        service = None
        result['errors'].append(f'OAuth refresh could not verify processing: {type(exc).__name__}')
    for index, source in enumerate(rows, 1):
        vid = source.get('video_id')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(vid)):
            result['errors'].append({'index': index, 'error': source.get('error', 'No actual insert ID')})
            continue
        row = {'index': index, 'video_id': vid, 'youtube_url': f'https://youtu.be/{vid}',
               'title': source.get('title'), 'narration': source.get('narration'),
               'publish_at': source.get('publish_at_utc', source.get('scheduled_publish_at_utc')),
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
    result['complete'] = result['accepted_count'] == 6 and all('media_check' in row and 'media_error' not in row for row in result['videos'])
    Path('maintenance').mkdir(exist_ok=True)
    Path('maintenance/latest-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with open(os.environ.get('GITHUB_STEP_SUMMARY', os.devnull), 'a', encoding='utf-8') as summary:
        summary.write(f"YouTube accepted: {result['accepted_count']}/6; processing verified: {result['processed_count']}/6\n\n")
        for row in result['videos']:
            summary.write(f"- [{row['title']}]({row['youtube_url']}): {row['upload_status']}\n")
    if not result['complete']:
        raise SystemExit('Six accepted complete videos are not yet verified; see maintenance/latest-verification.json')


if __name__ == '__main__':
    main()

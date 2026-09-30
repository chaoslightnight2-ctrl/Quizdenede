"""Read back completed inserts without retrying videos.insert."""
from __future__ import annotations
import re
import time
from googleapiclient.errors import HttpError


def confirm(service, video_id, *, attempts=12):
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(video_id)):
        raise ValueError("YouTube returned an invalid video ID")
    for attempt in range(attempts):
        try:
            response = service.videos().list(part='status,processingDetails', id=video_id).execute(num_retries=3)
        except HttpError as exc:
            if exc.resp.status == 403 and b'insufficientPermissions' in exc.content:
                # Upload-only OAuth consent cannot read private processing status.
                # The insert ID proves acceptance; never label this as processed.
                return {'upload_status': 'api_insert_confirmed', 'processing_status': 'readback_scope_unavailable'}
            raise
        items = response.get('items', [])
        if items:
            status = items[0].get('status', {})
            processing = items[0].get('processingDetails', {}).get('processingStatus', '')
            if status.get('uploadStatus') in ('failed', 'rejected', 'deleted') or processing in ('failed', 'terminated'):
                raise ValueError(f"YouTube rejected uploaded video {video_id}: {status}, processing={processing}")
            if status.get('uploadStatus') == 'processed' or processing == 'succeeded':
                return {'upload_status': 'youtube_processed', 'youtube_status': status, 'processing_status': processing}
        if attempt < attempts - 1:
            time.sleep(10)
    raise TimeoutError(f"YouTube accepted {video_id}, processing still pending; do not upload again")

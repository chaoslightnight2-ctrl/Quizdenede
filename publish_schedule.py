"""Choose a future publication slot without exceeding the daily target."""
from collections import Counter
from datetime import datetime, timedelta


def next_slot(now, records, target_count=3, *, preferred=None, hour=None):
    if target_count not in (3, 6):
        raise ValueError('Daily publication target must be 3 or 6')
    if now.tzinfo is None:
        raise ValueError('Publication clock must include its timezone')
    reserved = set()
    for row in records:
        if not row.get('video_id') or row.get('upload_status') == 'youtube_rejected':
            continue
        value = row.get('publish_at_local') or row.get('publish_at') or row.get('publish_at_utc')
        try:
            at = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if at.tzinfo is not None:
                reserved.add(at.astimezone(now.tzinfo))
        except (ValueError, TypeError):
            continue
    per_day = Counter(at.date() for at in reserved)
    minimum = now + timedelta(minutes=30)
    def free(at):
        return at > minimum and at not in reserved and per_day[at.date()] < target_count
    if preferred is not None:
        preferred = preferred.astimezone(now.tzinfo)
        if free(preferred) and preferred.hour in range(0, 24, 24 // target_count):
            return preferred
    hours = [hour] if hour is not None else range(0, 24, 24 // target_count)
    for offset in range(31):
        for slot_hour in hours:
            at = (now + timedelta(days=offset)).replace(hour=slot_hour, minute=0, second=0, microsecond=0)
            if free(at):
                return at
    raise RuntimeError('No free future publication slot within 31 days')

"""Choose a future publication slot without exceeding the daily target."""
from collections import Counter
from datetime import datetime, timedelta


# Europe/Istanbul publication hours: three evenly spaced evening slots.
# These are an initial experiment, not a measured national Shorts peak.
PUBLICATION_HOURS = {3: (19, 21, 23), 6: (12, 15, 17, 19, 21, 23)}


def publication_hours(target_count=3):
    try:
        return PUBLICATION_HOURS[target_count]
    except KeyError:
        raise ValueError('Daily publication target must be 3 or 6') from None


def next_slot(now, records, target_count=3, *, preferred=None, hour=None):
    configured_hours = publication_hours(target_count)
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
        if free(preferred) and preferred.hour in configured_hours and preferred.minute == 0:
            return preferred
    hours = [hour] if hour in configured_hours else configured_hours
    for offset in range(31):
        for slot_hour in hours:
            at = (now + timedelta(days=offset)).replace(hour=slot_hour, minute=0, second=0, microsecond=0)
            if free(at):
                return at
    raise RuntimeError('No free future publication slot within 31 days')


def daily_receipts(now, records):
    """Count unique accepted IDs for this local publication date, including old slots."""
    selected = {}
    for row in records:
        if not row.get('video_id') or row.get('upload_status') == 'youtube_rejected':
            continue
        value = row.get('publish_at_local') or row.get('publish_at') or row.get('publish_at_utc')
        try:
            at = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if at.tzinfo is not None and at.astimezone(now.tzinfo).date() == now.date():
                selected[row['video_id']] = row
        except (ValueError, TypeError):
            continue
    return list(selected.values())

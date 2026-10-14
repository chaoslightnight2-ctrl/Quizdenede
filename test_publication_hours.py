import unittest
from datetime import datetime, timedelta, timezone
try:
    from src.publish_schedule import next_slot, publication_hours
except ImportError:
    from publish_schedule import next_slot, publication_hours

TZ = timezone(timedelta(hours=3))


class AudiencePublicationHoursTests(unittest.TestCase):
    def test_midnight_generation_reserves_lunch_and_evening_without_duplicates(self):
        now = datetime(2026, 10, 15, 0, 5, tzinfo=TZ)
        rows = []
        planned = []
        for index in range(3):
            at = next_slot(now, rows)
            planned.append(at)
            rows.append({'video_id': str(index), 'publish_at_local': at.isoformat()})
        self.assertEqual([at.hour for at in planned], [12, 19, 21])
        self.assertTrue(all(at.date() == now.date() for at in planned))
        self.assertEqual(planned[1].astimezone(timezone.utc).hour, 16)

    def test_late_render_uses_next_evening_slot(self):
        now = datetime(2026, 10, 15, 18, 45, tzinfo=TZ)
        self.assertEqual(next_slot(now, []).hour, 21)

    def test_old_preferred_hour_cannot_restore_midnight_publication(self):
        now = datetime(2026, 10, 15, 0, 5, tzinfo=TZ)
        self.assertEqual(next_slot(now, [], preferred=now.replace(hour=8)).hour, 12)
        self.assertEqual(next_slot(now, [], hour=8).hour, 12)

    def test_old_receipts_still_count_toward_daily_limit(self):
        now = datetime(2026, 10, 15, 1, tzinfo=TZ)
        rows = [{'video_id': str(h), 'publish_at_local': now.replace(hour=h).isoformat()} for h in (0, 8, 16)]
        self.assertEqual(next_slot(now, rows), datetime(2026, 10, 16, 12, tzinfo=TZ))

    def test_six_video_mode_has_six_distinct_daytime_evening_hours(self):
        self.assertEqual(publication_hours(6), (12, 15, 17, 19, 21, 23))


if __name__ == '__main__':
    unittest.main()

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'freefaceless':
    ROOT = ROOT.parent
spec = importlib.util.spec_from_file_location('public_delivery', ROOT / 'maintenance/check_public_delivery.py')
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class PublicDeliveryTests(unittest.TestCase):
    def feed(self, published, updated='2026-10-15T18:30:00Z'):
        return f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"><entry><yt:videoId>real-video-id</yt:videoId><title>Actual public video</title><published>{published}</published><updated>{updated}</updated></entry></feed>'

    def test_editing_an_old_video_does_not_count_as_a_new_publication(self):
        result = delivery.inspect_feed(self.feed('2026-10-08T13:00:00Z'), datetime(2026, 10, 15, 18, 30, tzinfo=timezone.utc), (19, 21, 23))
        self.assertEqual(result['minimum_publications_due'], 2)
        self.assertEqual(result['public_count_today'], 0)
        self.assertFalse(result['public_delivery_verified'])

    def test_local_day_counts_and_future_slots_are_not_reported_as_missed(self):
        result = delivery.inspect_feed(self.feed('2026-10-14T21:00:34Z'), datetime(2026, 10, 15, 16, 30, tzinfo=timezone.utc), (19, 21, 23))
        self.assertEqual(result['public_count_today'], 1)
        self.assertEqual(result['minimum_publications_due'], 1)
        self.assertTrue(result['public_delivery_verified'])

    def test_an_insert_receipt_without_a_public_entry_never_counts(self):
        xml = '<feed xmlns="http://www.w3.org/2005/Atom" />'
        result = delivery.inspect_feed(xml, datetime(2026, 10, 15, 20, 30, tzinfo=timezone.utc), (19, 21, 23))
        self.assertEqual(result['public_count_today'], 0)
        self.assertEqual(result['minimum_publications_due'], 3)
        self.assertFalse(result['public_delivery_verified'])

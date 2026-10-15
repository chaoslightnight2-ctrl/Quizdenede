import copy
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch
import test_publish_runtime as fixtures


class DailyResumeTests(unittest.TestCase):
    def fixture(self):
        return fixtures.PublishingTests().fixture()

    def test_partial_day_only_uploads_the_missing_slot(self):
        runtime, bot, memory, inserted, clock = self.fixture()
        memory['history.json'] = {'processed_news': [
            {'video_id': f'old-{h}', 'publish_at_local': clock[0].replace(hour=h).isoformat()} for h in (19, 21)]}
        with patch.dict('os.environ', {'DAILY_VIDEO_COUNT': '3', 'DRY_RUN': '0', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch('upload_recovery.requested', return_value=False), \
             patch.object(runtime, 'confirm', return_value={'upload_status': 'api_insert_confirmed'}):
            runtime.run(bot)
        self.assertEqual(len(inserted), 1)
        self.assertEqual(inserted[0][1].hour, 23)
        self.assertEqual(memory['run_report.json']['daily_existing_count'], 2)
        self.assertEqual(memory['run_report.json']['target_count'], 1)

    def test_completed_day_does_not_generate_or_upload_again(self):
        runtime, bot, memory, inserted, clock = self.fixture()
        memory['history.json'] = {'processed_news': [
            {'video_id': f'old-{h}', 'publish_at_local': clock[0].replace(hour=h).isoformat()} for h in (19, 21, 23)]}
        bot.fetch_news_pool = Mock(side_effect=AssertionError('must not fetch'))
        bot.generate_news_script = Mock(side_effect=AssertionError('must not generate'))
        with patch.dict('os.environ', {'DRY_RUN': '0', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch('upload_recovery.requested', return_value=False):
            runtime.run(bot)
        self.assertEqual(inserted, [])
        self.assertTrue(memory['run_report.json']['daily_target_satisfied'])

    def test_saved_ready_content_publishes_without_a_new_generation_call(self):
        runtime, bot, memory, inserted, clock = self.fixture()
        queued = {'fingerprint': 'saved', 'title': 'Saved real draft', 'script': 'temiz metin', 'spoken_text': 'temiz metin'}
        memory['selected.json'] = {'generated_at': clock[0].isoformat(), 'selected_news': [queued]}
        memory['history.json'] = {'processed_news': [
            {'video_id': f'old-{h}', 'publish_at_local': clock[0].replace(hour=h).isoformat()} for h in (19, 21)]}
        bot.fetch_news_pool = Mock(side_effect=AssertionError('must not fetch'))
        bot.generate_news_script = Mock(side_effect=AssertionError('must not regenerate'))
        with patch.dict('os.environ', {'DRY_RUN': '0', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch('upload_recovery.requested', return_value=False), \
             patch.object(runtime, 'confirm', return_value={'upload_status': 'api_insert_confirmed'}):
            runtime.run(bot)
        self.assertEqual([row[0] for row in inserted], ['saved'])


if __name__ == '__main__':
    unittest.main()

import copy
import os
import unittest
from unittest.mock import patch
import test_publish_runtime as fixtures


class BatchSavingsTests(unittest.TestCase):
    def test_failed_saved_item_is_not_generated_and_rendered_twice(self):
        runtime, bot, memory, inserted, clock = fixtures.PublishingTests().fixture()
        memory['selected.json'] = {'generated_at': clock[0].isoformat(), 'selected_news': [
            {'fingerprint': '0', 'title': 'Saved source', 'script': 'metin', 'spoken_text': 'metin', 'generation_mode': 'prompt_first_v1'}]}
        generated = []
        rendered = []
        def generate(item):
            generated.append(item['fingerprint'])
            return 'metin'
        def render(item, index):
            rendered.append(item['fingerprint'])
            if item['fingerprint'] == '0':
                raise RuntimeError('render temporarily unavailable')
            return {'video_path': f'short_{index}.mp4'}
        bot.generate_news_script, bot.build_video_for_item = generate, render
        with patch.dict(os.environ, {'DAILY_VIDEO_COUNT': '3', 'DRY_RUN': '0', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch('upload_recovery.requested', return_value=False), patch.object(runtime.time, 'sleep'), \
             patch.object(runtime, 'confirm', return_value={'upload_status': 'api_insert_confirmed'}):
            runtime.run(bot)
        self.assertEqual(generated, ['1', '2', '3'])
        self.assertEqual(rendered.count('0'), 3)
        self.assertEqual([row[0] for row in inserted], ['1', '2', '3'])

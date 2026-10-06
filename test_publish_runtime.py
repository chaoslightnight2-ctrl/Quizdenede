import copy
import importlib.util
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import types
import unittest
from unittest.mock import patch
import requests
import json
import tempfile
from publish_schedule import next_slot


TZ = timezone(timedelta(hours=3))


class PublishingTests(unittest.TestCase):
    def fixture(self):
        import batch_runtime
        memory, inserted = {}, []
        items = [{'fingerprint': str(i), 'title': f'Konu {i}', 'spoken_text': 'temiz metin'} for i in range(4)]
        clock = [datetime(2026, 10, 6, 1, tzinfo=TZ)]
        bot = types.SimpleNamespace(__doc__='global test', logger=logging.getLogger('test'), HISTORY_FILE=Path('history.json'),
            SELECTED_FILE=Path('selected.json'), PLAN_FILE=Path('plan.json'), now_tr=lambda: clock[0],
            fetch_news_pool=lambda **kwargs: items, choose_six=lambda pool, history: pool,
            load_json=lambda path, default: copy.deepcopy(memory.get(str(path), default)),
            save_json=lambda path, value: memory.update({str(path): copy.deepcopy(value)}),
            generate_news_script=lambda item: 'temiz metin', build_video_for_item=lambda item, index: {'video_path': f'short_{index}.mp4'},
            get_youtube_service=lambda: None)
        def insert(path, item, at):
            inserted.append((item['fingerprint'], at))
            return {'video_id': 'AbcDef_000' + item['fingerprint'], 'youtube_url': 'test', 'publish_at_local': at.isoformat()}
        bot.upload_to_youtube = insert
        def update(history, selected):
            history.setdefault('processed_news', []).extend(copy.deepcopy(selected))
            return history
        bot.update_history = update
        return batch_runtime, bot, memory, inserted, clock

    def test_first_insert_is_saved_before_second_source_validation(self):
        runtime, bot, memory, inserted, clock = self.fixture()
        def generate(item):
            if item['fingerprint'] == '1':
                self.assertEqual(inserted[0][0], '0')
                self.assertEqual(memory['history.json']['processed_news'][0]['video_id'], 'AbcDef_0000')
                raise ValueError('real source unsupported')
            return 'temiz metin'
        bot.generate_news_script = generate
        with patch.dict(os.environ, {'DRY_RUN': '0', 'DAILY_VIDEO_COUNT': '3', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(runtime, 'confirm', return_value={'upload_status': 'api_insert_confirmed'}):
            runtime.run(bot)
        self.assertEqual([row[0] for row in inserted], ['0', '2', '3'])
        self.assertEqual([row[1].hour for row in inserted], [8, 16, 0])
        self.assertTrue(memory['run_report.json']['complete'])
        self.assertEqual(memory['run_report.json']['target_count'], 3)

    def test_quota_stop_keeps_previous_actual_insert(self):
        runtime, bot, memory, inserted, clock = self.fixture()
        def generate(item):
            if item['fingerprint'] == '1':
                raise requests.HTTPError('HTTP 429')
            return 'temiz metin'
        bot.generate_news_script = generate
        with patch.dict(os.environ, {'DRY_RUN': '0', 'DAILY_VIDEO_COUNT': '3', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(runtime, 'confirm', return_value={'upload_status': 'api_insert_confirmed'}), \
             self.assertRaises(requests.HTTPError):
            runtime.run(bot)
        self.assertEqual(len(inserted), 1)
        self.assertEqual(len(memory['history.json']['processed_news']), 1)
        self.assertFalse(memory['run_report.json']['complete'])

    def test_render_wait_refreshes_expired_publication_time(self):
        runtime, bot, memory, inserted, clock = self.fixture()
        def build(item, index):
            clock[0] = datetime(2026, 10, 6, 8, 5, tzinfo=TZ)
            return {'video_path': f'short_{index}.mp4'}
        bot.build_video_for_item = build
        with patch.dict(os.environ, {'DRY_RUN': '0', 'DAILY_VIDEO_COUNT': '3', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(runtime, 'confirm', return_value={'upload_status': 'api_insert_confirmed'}):
            runtime.run(bot)
        self.assertEqual(inserted[0][1].hour, 16)
        self.assertTrue(all(at > clock[0] + timedelta(minutes=30) for _, at in inserted))

    def test_legacy_three_receipts_fill_today_even_on_old_hours(self):
        now = datetime(2026, 10, 6, 6, tzinfo=TZ)
        rows = [{'video_id': str(hour), 'publish_at_local': now.replace(hour=hour).isoformat()} for hour in (4, 12, 20)]
        at = next_slot(now, rows, 3)
        self.assertEqual(at, datetime(2026, 10, 7, tzinfo=TZ))

    def test_expired_preferred_slot_moves_to_next_eight_hour_slot(self):
        now = datetime(2026, 10, 6, 8, 5, tzinfo=TZ)
        at = next_slot(now, [], 3, preferred=now.replace(hour=8, minute=0))
        self.assertEqual(at.hour, 16)

    def test_quiz_generator_is_lazy_and_preserves_first_receipt(self):
        runtime, bot, memory, inserted, clock = self.fixture()
        def items(history, count):
            yield {'fingerprint': '0', 'title': 'Soru', 'spoken_text': 'temiz metin'}
            self.assertEqual(len(inserted), 1)
            self.assertEqual(len(memory['history.json']['processed_news']), 1)
            raise requests.HTTPError('HTTP 429')
        bot.iter_news_items = items
        bot.fetch_news_pool = lambda **kwargs: self.fail('quiz was eagerly generated')
        with patch.dict(os.environ, {'ENABLE_YOUTUBE_UPLOAD': '1', 'DAILY_VIDEO_COUNT': '3', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(runtime, 'confirm', return_value={'upload_status': 'api_insert_confirmed'}), self.assertRaises(requests.HTTPError):
            runtime.run(bot, quiz=True)
        self.assertEqual(len(inserted), 1)

    def test_future_insert_receipts_are_not_claimed_as_publication(self):
        filename = Path('maintenance/verify_existing_uploads.py').resolve()
        spec = importlib.util.spec_from_file_location('verify_under_test', filename)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = [{'video_id': f'AbcDef_000{i}', 'index': i + 1, 'title': 'Metin', 'publish_at_utc': '2050-01-01T00:00:00Z'} for i in range(3)]
            (root / 'run_report.json').write_text(json.dumps({'run_id': '42', 'target_count': 3, 'videos': rows}))
            for i in range(1, 4):
                (root / f'short_{i}.mp4').write_bytes(b'test media fixture')
            try:
                os.chdir(root)
                with patch('sys.argv', ['verify', '--source-run', '42', '--artifact-dir', str(root)]), \
                     patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(root / 'summary.md')}), \
                     patch.object(verifier, 'youtube_service', side_effect=RuntimeError('no OAuth scope')), \
                     patch.object(verifier, 'public_listing', return_value={}), \
                     patch.object(verifier, 'inspect_media', return_value={'duration': 30}), \
                     patch.object(verifier.subprocess, 'run'):
                    verifier.main()
                evidence = json.loads((root / 'maintenance/latest-verification.json').read_text())
            finally:
                os.chdir(previous)
        self.assertTrue(evidence['accepted_complete'])
        self.assertFalse(evidence['complete'])
        self.assertEqual(evidence['published_count'], 0)
        self.assertTrue(all(row['publication_status'] == 'scheduled_wait' for row in evidence['videos']))

    def test_json_repairs_keep_only_latest_failed_response(self):
        import groq_client
        bodies = []
        failures = iter(['FIRST_BAD', 'SECOND_BAD'])
        def post(*args, **kwargs):
            bodies.append(copy.deepcopy(kwargs['json']))
            if len(bodies) < 3:
                error = {'code': 'json_validate_failed', 'message': 'invalid', 'failed_generation': next(failures) * 600}
                return types.SimpleNamespace(status_code=400, json=lambda: {'error': error}, headers={}, text='')
            return types.SimpleNamespace(status_code=200, raise_for_status=lambda: None,
                json=lambda: {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}]})
        schema = groq_client.object_schema({'ok': {'type': 'boolean'}})
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-only', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(groq_client.requests, 'post', side_effect=post), patch.object(groq_client.time, 'sleep'):
            self.assertTrue(groq_client.chat_json('ORIGINAL SOURCE', schema=schema)['ok'])
        final = bodies[-1]['messages'][-1]['content']
        self.assertIn('ORIGINAL SOURCE', final)
        self.assertIn('SECOND_BAD', final)
        self.assertNotIn('FIRST_BAD', final)
        self.assertLess(len(final), 5000)


if __name__ == '__main__':
    unittest.main()

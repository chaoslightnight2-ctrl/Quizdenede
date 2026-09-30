import copy
import importlib.util
import logging
import os
from pathlib import Path
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from quality_gate import caption_chunks, spoken_text, validate_package, validate_visual_query
from groq_client import retry_delay
from voice_sync import validate_words


class QualityRegressionTests(unittest.TestCase):
    def test_four_repo_requests_use_distinct_minute_slots(self):
        from groq_client import request_slot
        self.assertEqual([request_slot(960, 960, i) for i in range(4)], [5, 65, 125, 185])
        self.assertEqual(request_slot(970, 1170, 0), 235)

    def test_strict_schema_is_sent_to_same_groq_model(self):
        import groq_client
        schema = {'type': 'object', 'properties': {'visual_query': {'type': 'string'}},
                  'required': ['visual_query'], 'additionalProperties': False}
        response = types.SimpleNamespace(status_code=200, raise_for_status=lambda: None,
            json=lambda: {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"visual_query":"moon surface space"}'}}]})
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-only', 'GROQ_MODEL': 'openai/gpt-oss-120b'}), \
             patch.object(groq_client.requests, 'post', return_value=response) as request, patch.object(groq_client.time, 'sleep'):
            groq_client.chat_json('test', schema=schema)
        body = request.call_args.kwargs['json']
        self.assertEqual(body['model'], 'openai/gpt-oss-120b')
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertEqual(body['response_format']['json_schema']['schema'], schema)

    def test_upload_only_consent_never_claims_processing_success(self):
        from youtube_receipt import confirm
        from googleapiclient.errors import HttpError
        error = HttpError(types.SimpleNamespace(status=403, reason='Forbidden'), b'{"error":{"errors":[{"reason":"insufficientPermissions"}]}}')
        service = types.SimpleNamespace(videos=lambda: types.SimpleNamespace(list=lambda **kw: types.SimpleNamespace(execute=lambda **kw: (_ for _ in ()).throw(error))))
        receipt = confirm(service, 'AbcDef_1234')
        self.assertEqual(receipt['upload_status'], 'api_insert_confirmed')
        self.assertEqual(receipt['processing_status'], 'readback_scope_unavailable')

    def test_visual_query_formatting_is_safe_but_turkish_not_transliterated(self):
        self.assertEqual(validate_visual_query('"istanbul city traffic"'), 'istanbul city traffic')
        with self.assertRaises(ValueError):
            validate_visual_query('İstanbul şehir trafiği')

    def test_final_caption_never_moves_word_without_timestamp(self):
        rows = [(i * .25, .2, word) for i, word in enumerate('bir iki üç dört beş'.split())]
        chunks = caption_chunks(rows)
        self.assertEqual(chunks[0][2], 'bir iki üç dört')
        self.assertEqual(chunks[1][0], 1.0)
        self.assertAlmostEqual(chunks[1][1], .2)
        self.assertEqual(chunks[1][2], 'beş')

    def test_numeric_punctuation_does_not_change_value(self):
        self.assertEqual(spoken_text('%45,5 arttı'), 'yüzde 45 virgül 5 arttı')
        self.assertEqual(spoken_text('1.000 kişi'), '1000 kişi')

    def test_caption_text_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_words('ses metni doğru', [(0, .2, 'ses'), (.2, .2, 'yanlış')])

    def test_server_long_cooldown_is_not_capped_to_thirty_seconds(self):
        response = types.SimpleNamespace(headers={'retry-after': '120'}, text='')
        self.assertGreaterEqual(retry_delay(response, 0), 120)

    def test_duplicate_cta_rejected_even_with_different_wording(self):
        with self.assertRaises(ValueError):
            validate_package(title='Ulaşımda yeni dönem', hook='Bu kararla şehir içi yolculuklar nasıl değişecek',
                narration='Belediye yeni ulaşım planının güzergahlarını açıkladı Ana hatlarda sefer düzeni değişiyor Yolcular durak bilgilerini kontrol edebilecek Güncel haberler için abone ol',
                cta='Global Haber kanalına abone ol', description='Şehir ulaşım planı yenilendi', channel_name='Global Haber')

    def test_sources_not_read_aloud(self):
        with self.assertRaises(ValueError):
            validate_package(title='Ulaşımda yeni dönem', hook='Bu kararla şehir içi yolculuklar nasıl değişecek',
                narration='Kaynakça www.haber.com Belediye yeni ulaşım planının güzergahlarını açıkladı Ana hatlarda sefer düzeni değişiyor Yolcular durak bilgilerini kontrol edebilecek',
                cta='Global Haber kanalına abone ol', description='Şehir ulaşım planı yenilendi', channel_name='Global Haber')

    def test_news_invalid_visual_query_is_repaired_with_same_groq(self):
        if not Path('news_generation.py').exists():
            self.skipTest('news only')
        import news_generation
        good = {'suitable': True, 'title': 'İstanbul trafiğinde yeni düzen nasıl işleyecek',
                'hook': 'İstanbul trafiğinde bu yeni düzen kimi etkileyecek',
                'narration_parts': ['Belediye ana caddelerde yeni trafik düzenini duyurdu Otobüsler belirlenen güzergahlardan geçecek Yolcular değişen durakları kontrol edebilecek',
                                    'Düzenlemenin amacı şehir içi ulaşımı kolaylaştırmak Yeni güzergah bilgileri yolcularla paylaşıldı Plan ana caddeleri kapsıyor'],
                'cta': 'Global Haber kanalına abone ol', 'description': 'İstanbul ulaşım düzeni yenilendi Bu değişiklik sizin yolculuğunuzu nasıl etkiler',
                'visual_query': 'istanbul city traffic', 'topic_bucket': 'transport_cities',
                'tags': ['istanbul trafik', 'otobüs', 'ulaşım', 'güzergah', 'durak'], 'hashtags': ['#shorts', '#İstanbul', '#Ulaşım']}
        bad = copy.deepcopy(good)
        bad['visual_query'] = 'İstanbul şehir trafiği'
        source = 'Belediye ana caddelerde yeni trafik düzenini duyurdu Otobüsler belirlenen güzergahlardan geçecek Yolcular değişen durakları kontrol edebilecek Düzenlemenin amacı şehir içi ulaşımı kolaylaştırmak Yeni güzergah bilgileri yolcularla paylaşıldı Plan ana caddeleri kapsıyor'
        item = {'title': 'İstanbul trafik düzeni', 'summary': source}
        with patch.object(news_generation, 'chat_json', side_effect=[bad, good, {'valid': True, 'reason': 'supported'}]) as request:
            result = news_generation.generate(item, types.SimpleNamespace(logger=logging.getLogger('test')), 'Global Haber')
        self.assertEqual(request.call_count, 3)
        self.assertNotIn('şeh', item['visual_query'])
        self.assertEqual(result, item['spoken_text'])

    def test_quiz_keeps_valid_candidates_between_rounds(self):
        if not Path('run_quiz_main.py').exists():
            self.skipTest('quiz only')
        import sys
        stub = types.ModuleType('main')
        stub.update_history = lambda history, selected: history
        stub.upload_to_youtube = lambda *args: None
        stub.logger = logging.getLogger('test')
        with patch.dict(sys.modules, {'main': stub}):
            spec = importlib.util.spec_from_file_location('quiz_under_test', 'run_quiz_main.py')
            quiz = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(quiz)
        candidates = [{'id': str(i), 'question': f'Birbirinden farklı doğru soru {i} nedir', 'answer': 'a', 'explanation': 'Açıklama gerekli bilgileri net veriyor', 'topic': str(i)} for i in range(6)]
        with patch.object(quiz, '_generate_candidate_round', side_effect=[candidates[:4], candidates[4:]]):
            result = quiz.generate_questions({'processed_questions': []})
        self.assertEqual(len(result), 6)
        self.assertTrue(quiz.is_good_question('Bu uzun sorunun kesin ve tek cevabı ne olabilir', 'a', 'Burada gerekçe yanıttan farklı kelimelerle açıklanıyor')[0])

    def test_partial_uploads_persist_and_do_not_reinsert_after_readback_failure(self):
        import batch_runtime
        store = {}
        inserted = []
        items = [{'fingerprint': str(i), 'title': f'Konu {i}', 'url': f'https://example.org/{i}', 'published_at': '2026-09-30', 'spoken_text': 'temiz metin'} for i in range(6)]
        bot = types.SimpleNamespace(__doc__='global test', logger=logging.getLogger('test'), HISTORY_FILE=Path('history.json'),
            PLAN_FILE=Path('plan.json'), SELECTED_FILE=Path('selected.json'), now_tr=lambda: datetime(2026, 9, 30, tzinfo=timezone.utc),
            fetch_news_pool=lambda **kwargs: items, choose_six=lambda pool, history: pool,
            load_json=lambda file, default: copy.deepcopy(store.get(str(file), default)),
            save_json=lambda file, value: store.update({str(file): copy.deepcopy(value)}),
            generate_news_script=lambda item: 'temiz metin', build_video_for_item=lambda item, index: {'video_path': 'test.mp4'},
            get_youtube_service=lambda: None)
        def upload(path, item, at):
            inserted.append(item['fingerprint'])
            return {'video_id': 'video-id-' + item['fingerprint'], 'youtube_url': 'test', 'publish_at_local': at.isoformat()}
        def history_update(history, selected):
            history.setdefault('processed_news', []).extend(copy.deepcopy(selected))
            return history
        bot.upload_to_youtube = upload
        bot.update_history = history_update
        with patch.dict(os.environ, {'DRY_RUN': '0'}), patch.object(batch_runtime, 'confirm', side_effect=TimeoutError('pending')):
            batch_runtime.run(bot)
        self.assertEqual(inserted, [str(i) for i in range(6)])
        self.assertEqual(len(store['history.json']['processed_news']), 6)
        self.assertEqual(len(store['run_report.json']['videos']), 6)
        self.assertTrue(store['run_report.json']['complete'])
        self.assertTrue(all(row['upload_status'] == 'api_insert_confirmed' for row in store['run_report.json']['videos']))

    def test_dry_run_never_updates_upload_history(self):
        import batch_runtime
        items = [{'fingerprint': str(i), 'title': 'Konu', 'spoken_text': 'metin'} for i in range(6)]
        bot = types.SimpleNamespace(__doc__='global test', logger=logging.getLogger('test'), HISTORY_FILE=Path('history.json'),
            PLAN_FILE=Path('plan.json'), SELECTED_FILE=Path('selected.json'), now_tr=lambda: datetime(2026, 9, 30, tzinfo=timezone.utc),
            fetch_news_pool=lambda **kwargs: items, choose_six=lambda pool, history: pool,
            load_json=lambda file, default: default, save_json=lambda file, value: None,
            generate_news_script=lambda item: 'metin', build_video_for_item=lambda item, index: {'video_path': 'test.mp4'},
            upload_to_youtube=lambda path, item, at: {'video_id': 'dry-run', 'youtube_url': 'test', 'publish_at_local': at.isoformat()},
            update_history=lambda *args: self.fail('dry run modified real history'))
        with patch.dict(os.environ, {'DRY_RUN': '1'}):
            batch_runtime.run(bot)


if __name__ == '__main__':
    unittest.main()

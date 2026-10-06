import importlib.util
import logging
import sys
import types
import unittest
from unittest.mock import patch
from quiz_presentation import question_end, answer_start, question_image, install

class QuestionFirstTests(unittest.TestCase):
    def test_question_once_before_pause_and_short_cta(self):
        stub = types.ModuleType('main')
        stub.update_history = lambda history, selected: history
        stub.upload_to_youtube = lambda *args: None
        stub.logger = logging.getLogger('test')
        with patch.dict(sys.modules, {'main': stub}):
            spec = importlib.util.spec_from_file_location('question_first_test_module', 'run_quiz_main.py')
            quiz = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(quiz)
        q = 'Güneş sistemindeki en büyük gezegen hangisidir'
        item = {'title': q, 'quiz': {'question': q, 'answer': 'Jüpiter', 'topic': 'bilim', 'explanation': 'Bu gaz devi çevresindeki çok sayıda uyduyla birlikte Güneş etrafında döner'}}
        spoken = quiz.generate_news_script(item)
        self.assertTrue(spoken.startswith(q))
        self.assertEqual(spoken.count(q), 1)
        self.assertEqual(item['tts_text'].count(q), 1)
        self.assertNotIn('İlk tahminine güveniyor musun', spoken)
        self.assertIn('sana üç saniye veriyorum', spoken)
        self.assertTrue(spoken.endswith('Zekanı Test Et kanalına abone ol'))
        self.assertEqual(item['hook_style'], 'question_first')

    def test_overlay_uses_start_plus_duration_and_actual_answer_onset(self):
        words = [(0.1, .3, 'Hangi'), (.5, .4, 'gezegen'), (1, .2, 'düşün'), (4.3, .3, 'Doğru'), (4.6, .2, 'cevap')]
        self.assertAlmostEqual(question_end('Hangi gezegen', words), .9)
        self.assertAlmostEqual(answer_start(words), 4.3)

    def test_question_bitmap_has_visible_text_and_fits(self):
        from pathlib import Path
        font = next((str(p) for p in [Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'), Path('C:/Windows/Fonts/arialbd.ttf')] if p.exists()), None)
        if not font:
            self.skipTest('system font unavailable')
        image = question_image('Güneş sistemindeki en büyük gezegen hangisidir', font)
        self.assertEqual(image.width, 940)
        self.assertLess(image.height, 360)
        self.assertGreater(image.getchannel('A').getextrema()[1], 160)

    def test_caption_wrapper_restores_grouping_after_render_error(self):
        words = [(0.1, .2, 'Hangi'), (.4, .2, 'gezegen'), (4, .2, 'Doğru'), (4.2, .2, 'cevap')]
        def chunks(rows):
            return rows
        def assemble(*args):
            self.assertEqual(bot.chunk_timestamps(words), words[2:])
            raise RuntimeError('render interrupted')
        def build(item, index):
            return bot.assemble_video(None, None, None, words)
        bot = types.SimpleNamespace(build_video_for_item=build, assemble_video=assemble, generate_captions=lambda rows: [], chunk_timestamps=chunks)
        install(bot)
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            bot.build_video_for_item({'question_text': 'Hangi gezegen'}, 1)
        self.assertIs(bot.chunk_timestamps, chunks)

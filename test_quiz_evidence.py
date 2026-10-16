import importlib.util
import logging
import sys
import types
import unittest
from unittest.mock import patch


class QuizEvidenceTests(unittest.TestCase):
    def load(self):
        stub = types.SimpleNamespace(update_history=lambda *a: None, upload_to_youtube=lambda *a: None,
                                     logger=logging.getLogger('test'))
        with patch.dict(sys.modules, {'main': stub}):
            spec = importlib.util.spec_from_file_location('quiz_evidence_test', 'run_quiz_main.py')
            quiz = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(quiz)
        return quiz

    def test_editor_must_supply_real_evidence_for_the_bound_source(self):
        quiz = self.load()
        candidate = {'id': 'candidate', 'source_id': 'one', 'question': 'Dünyanın uydusu hangisidir', 'answer': 'Ay', 'explanation': 'Ay Dünya çevresinde dolanır'}
        sources = [{'id': 'one', 'text': 'The Moon orbits Earth.'},
                   {'id': 'two', 'text': 'Earth orbits the Sun.'}]
        verdict = {'id': 'candidate', 'valid': True, 'source_quote': 'The Moon orbits Earth.',
                   'requested_information': 'Dünyanın uydusu', 'independent_answer': 'Ay', 'evidence': [
                       {'field': key, 'supported': True, 'source_quote': 'The Moon orbits Earth.'}
                       for key in ('question', 'answer', 'explanation')]}
        cases = [(verdict, True), (dict(verdict, source_quote='Earth orbits the Sun.'), False),
                 (dict(verdict, source_quote='An invented quotation'), False),
                 (dict(verdict, independent_answer=''), False),
                 (dict(verdict, independent_answer='Güneş'), False)]
        for row, expected in cases:
            with self.subTest(row=row), patch.object(quiz, 'chat_json', return_value={'checks': [row]}):
                result = quiz.verify_questions([candidate], sources)
                self.assertEqual(len(result), 1 if expected else 0)
                if expected:
                    quiz.verify_approved_quiz(result[0])
                    changed = dict(result[0], answer='Güneş')
                    with self.assertRaises(ValueError):
                        quiz.verify_approved_quiz(changed)
        with patch.object(quiz, 'chat_json', return_value={'checks': [verdict, dict(verdict, valid=False)]}):
            self.assertEqual(quiz.verify_questions([candidate], sources), [])

    def test_unreviewed_quiz_cannot_reach_render_or_upload(self):
        quiz = self.load()
        from unittest.mock import Mock
        quiz.bot.get_youtube_service = Mock()
        item = {'title': 'Soru', 'quiz': {'question': 'Dünyanın uydusu hangisidir', 'answer': 'Ay', 'explanation': 'Ay Dünya çevresinde dolanır'}}
        with self.assertRaises(ValueError):
            quiz.generate_news_script(item)
        with patch.object(quiz, 'validate_rendered_video') as render:
            with self.assertRaises(ValueError):
                quiz.upload_to_youtube('nonexistent.mp4', item, None)
            render.assert_not_called()
        quiz.bot.get_youtube_service.assert_not_called()

    def test_attaching_approval_does_not_mark_a_verified_quiz_as_rejected(self):
        quiz = self.load()
        question = 'Güneş sistemindeki en büyük gezegen hangisidir'
        raw = {'question': question, 'answer': 'Jüpiter', 'topic': 'bilim', 'explanation': 'Jüpiter Güneş çevresinde dolanan bir gaz devidir',
               'visual_query': 'jupiter planet space', 'source_id': 'one', 'hashtags': ['gezegen', 'uzay']}
        approved = dict(raw, question=quiz.clean_question(question), id=quiz.make_id(quiz.clean_question(question), 'Jüpiter'),
                        publication_approval={'version': 2}, editorial_review={'valid': True})
        history = {'requested_count': 1}
        source = {'id': 'one', 'title': 'Planet fixture', 'text': 'Jupiter is a gas giant.', 'url': 'https://example.test/planet'}
        with patch.object(quiz, 'GROQ_API_KEY', 'test-only'), patch.object(quiz, 'fetch_sources', return_value=[source]), \
             patch.object(quiz, 'chat_json', return_value={'questions': [raw]}), patch.object(quiz, 'verify_questions', return_value=[approved]):
            self.assertEqual(len(quiz._generate_candidate_round(history)), 1)
        self.assertEqual(history['generation_feedback'], [])

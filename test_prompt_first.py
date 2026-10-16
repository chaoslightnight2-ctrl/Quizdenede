import importlib.util
import logging
import sys
import types
import unittest
from unittest.mock import patch

class PromptFirstQuizTests(unittest.TestCase):
    def load(self):
        stub = types.SimpleNamespace(update_history=lambda *a: None, upload_to_youtube=lambda *a: None,
                                     logger=logging.getLogger('test'))
        with patch.dict(sys.modules, {'main': stub}):
            spec = importlib.util.spec_from_file_location('prompt_first_quiz', 'run_quiz_main.py')
            quiz = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(quiz)
        return quiz

    def test_one_response_supplies_question_answer_explanation_without_critic(self):
        quiz = self.load()
        raw = {'question': 'Dünyanın doğal uydusu hangisidir', 'answer': 'Ay', 'topic': 'bilim',
               'explanation': 'Ay Dünya çevresinde dolanır', 'visual_query': 'moon earth orbit',
               'source_id': 'one', 'hashtags': ['Ay', 'uzay']}
        source = {'id': 'one', 'title': 'Moon', 'text': 'The Moon orbits Earth.'}
        with patch.object(quiz, 'GROQ_API_KEY', 'test-only'), patch.object(quiz, 'fetch_sources', return_value=[source]), \
             patch.object(quiz, 'chat_json', return_value={'questions': [raw]}) as request:
            questions = quiz.generate_questions({'requested_count': 1})
            item = {'title': raw['question'], 'quiz': questions[0]}
            spoken = quiz.generate_news_script(item)
        request.assert_called_once()
        self.assertIn('Doğru cevap Ay', spoken)
        self.assertNotIn('editorial_review', questions[0])
        self.assertNotIn('publication_approval', questions[0])
        self.assertIn(source['text'], request.call_args.args[0])

    def test_technical_generation_failure_has_no_retry_round(self):
        quiz = self.load()
        with patch.object(quiz, '_generate_candidate_round', side_effect=ValueError('broken JSON fields')) as request:
            with self.assertRaises(ValueError):
                quiz.generate_questions({'requested_count': 1})
        request.assert_called_once()

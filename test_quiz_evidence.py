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
        candidate = {'id': 'candidate', 'source_id': 'one'}
        sources = [{'id': 'one', 'text': 'The Moon orbits Earth.'},
                   {'id': 'two', 'text': 'Earth orbits the Sun.'}]
        verdict = {'id': 'candidate', 'valid': True, 'source_quote': 'The Moon orbits Earth.',
                   'requested_information': 'Dünyanın uydusu', 'independent_answer': 'Ay'}
        cases = [(verdict, True), (dict(verdict, source_quote='Earth orbits the Sun.'), False),
                 (dict(verdict, source_quote='An invented quotation'), False),
                 (dict(verdict, independent_answer=''), False)]
        for row, expected in cases:
            with self.subTest(row=row), patch.object(quiz, 'chat_json', return_value={'checks': [row]}):
                self.assertEqual(quiz.verify_questions([candidate], sources), [candidate] if expected else [])
        with patch.object(quiz, 'chat_json', return_value={'checks': [verdict, dict(verdict, valid=False)]}):
            self.assertEqual(quiz.verify_questions([candidate], sources), [])

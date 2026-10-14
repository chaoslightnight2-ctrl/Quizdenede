import ast
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest


class HistoryLoadingTests(unittest.TestCase):
    def loader(self):
        # Execute the actual loader without starting the video bot at import time.
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'load_json')
        namespace = {'Path': Path, 'Any': Any, 'json': json, 'HISTORY_FILE': Path('news_history.json')}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'main.py', 'exec'), namespace)
        return namespace['load_json']

    def test_existing_conflicted_history_never_becomes_an_empty_new_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'news_history.json'
            raw = '<<<<<<< Updated upstream\n{"processed_news": [{"video_id": "actual-id"}]}\n=======\n{}\n>>>>>>> Stashed changes'
            path.write_text(raw)
            with self.assertRaisesRegex(ValueError, 'preserve receipts'):
                self.loader()(path, {'processed_news': []})
            self.assertEqual(path.read_text(), raw)

    def test_valid_receipts_and_initial_missing_history_still_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'news_history.json'
            load = self.loader()
            self.assertEqual(load(path, {'processed_news': []}), {'processed_news': []})
            saved = {'processed_news': [{'video_id': 'actual-id'}]}
            path.write_text(json.dumps(saved))
            self.assertEqual(load(path, {}), saved)

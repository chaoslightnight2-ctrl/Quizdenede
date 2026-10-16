import ast
import copy
import hashlib
import json
import os
import re
import time
import types
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import requests


class TextAuditBudgetTests(unittest.TestCase):
    def load(self, name):
        path = Path('maintenance/text_only_audit.py')
        if not path.exists():
            path = Path('../maintenance/text_only_audit.py')
        tree = ast.parse(path.read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        namespace = dict(Path=Path, os=os, json=json, hashlib=hashlib, time=time, re=re, copy=copy,
                         report={'raw_groq_responses': []}, save=Mock())
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), namespace)
        return namespace[name], namespace

    def client(self):
        return types.SimpleNamespace(URL='https://api.groq.com/openai/v1/chat/completions',
            requests=types.SimpleNamespace(post=Mock(return_value=types.SimpleNamespace(status_code=200))),
            GroqQuotaError=requests.HTTPError, chat_json=Mock(return_value={'ok': True}))

    def test_only_two_groq_attempts_and_other_post_requests_do_not_consume_budget(self):
        function, namespace = self.load('record_client')
        client = self.client()
        post = client.requests.post
        with patch.dict(os.environ, {'GROQ_API_KEY': 'offline-key'}):
            function(client)
            client.requests.post('https://example.test/source-resolution')
            client.requests.post(client.URL)
            client.requests.post(client.URL)
            with self.assertRaises(requests.HTTPError):
                client.requests.post(client.URL)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(namespace['report']['groq_http_requests'], 2)

    def test_saved_cooldown_stops_before_any_http_request(self):
        function, namespace = self.load('record_client')
        client = self.client()
        with TemporaryDirectory() as folder:
            diagnostic = Path(folder) / 'quota.json'
            diagnostic.write_text(json.dumps({'key_fingerprint': hashlib.sha256(b'offline-key').hexdigest()[:16],
                                              'model': 'openai/gpt-oss-120b', 'not_before': time.time() + 3600}))
            namespace['Path'] = lambda *args: diagnostic
            with patch.dict(os.environ, {'GROQ_API_KEY': 'offline-key', 'GROQ_MODEL': 'openai/gpt-oss-120b'}):
                with self.assertRaises(requests.HTTPError):
                    function(client)
        client.requests.post.assert_not_called()
        self.assertEqual(namespace['report']['groq_http_requests'], 0)

    def test_fact_reference_focus_and_cache_reset_are_preserved(self):
        function, namespace = self.load('record_references')
        original = Mock(return_value=[{'id': 'source', 'text': 'actual test input'}])
        original.cache_clear = Mock()
        module = types.SimpleNamespace(fetch_sources=original)
        function(module)
        self.assertEqual(module.fetch_sources('science'), original.return_value)
        original.assert_called_once_with('science')
        module.fetch_sources.cache_clear()
        original.cache_clear.assert_called_once()

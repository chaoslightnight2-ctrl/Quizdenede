import copy
import hashlib
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
try:
    from src import groq_client as client
except ImportError:
    import groq_client as client


class QuotaDeferralTests(unittest.TestCase):
    def test_long_daily_limit_does_not_issue_eight_more_requests(self):
        response = types.SimpleNamespace(status_code=429, headers={'retry-after': '1800'},
                                         text='tokens per day TPD try again in 30m', json=lambda: {'error': {}})
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-only', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(client.requests, 'post', return_value=response) as post, \
             patch.object(client.time, 'sleep'):
            with self.assertRaises(client.GroqQuotaError):
                client.chat_json('source')
        self.assertEqual(post.call_count, 1)

    def test_saved_provider_cooldown_makes_no_api_call(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'diagnostic.json'
            target.write_text(json.dumps({'key_fingerprint': hashlib.sha256(b'test-only').hexdigest()[:16],
                                          'model': 'openai/gpt-oss-120b', 'not_before': 2000}))
            with patch.dict(os.environ, {'GROQ_API_KEY': 'test-only', 'PUBLISH_UPLOAD_CHECKPOINTS': '1', 'GROQ_MODEL': 'openai/gpt-oss-120b'}), \
                 patch.object(client, 'Path', return_value=target), patch.object(client.time, 'time', return_value=1000), \
                 patch.object(client.requests, 'post') as post:
                with self.assertRaises(client.GroqQuotaError):
                    client.chat_json('source')
            post.assert_not_called()

    def test_only_explicit_drafting_changes_reasoning_effort(self):
        bodies = []
        def post(*args, **kwargs):
            bodies.append(copy.deepcopy(kwargs['json']))
            return types.SimpleNamespace(status_code=200, json=lambda: {
                'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok": true}'}}]})
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-only', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(client.requests, 'post', side_effect=post), patch.object(client.time, 'sleep'):
            client.chat_json('draft', reasoning_effort='low')
            client.chat_json('editor')
        self.assertEqual([body['reasoning_effort'] for body in bodies], ['low', 'medium'])
        self.assertTrue(all(body['model'] == 'openai/gpt-oss-120b' for body in bodies))


if __name__ == '__main__':
    unittest.main()

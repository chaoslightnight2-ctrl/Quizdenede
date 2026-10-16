import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import requests

try:
    from src import groq_client as client, groq_budget as budget
except ImportError:
    import groq_client as client
    import groq_budget as budget


def reply(status=200, *, text=None, headers=None):
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    response._content = (text or json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}]})).encode()
    return response


class LowQuotaTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'GROQ_API_KEY': 'test-only', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_short_daily_or_minute_cooldown_stops_after_one_request(self):
        for message in ('tokens per day TPD try again in 2s', 'tokens per minute TPM try again in 10s'):
            with self.subTest(message=message), patch.object(client.time, 'sleep'), \
                 patch.object(client.requests, 'post', return_value=reply(429, text=json.dumps({'error': {'message': message}}))) as post:
                with self.assertRaises(client.GroqQuotaError):
                    client.chat_json('real source')
                self.assertEqual(post.call_count, 1)

    def test_request_daily_reset_is_not_hidden_by_short_token_reset(self):
        response = reply(429, headers={'retry-after': '2', 'x-ratelimit-reset-tokens': '5s',
                                      'x-ratelimit-reset-requests': '1h2m3s', 'x-ratelimit-remaining-requests': '0'})
        self.assertEqual(client.retry_delay(response, 0), 3724)

    def test_daily_request_reset_is_ignored_while_requests_remain(self):
        response = reply(429, headers={'retry-after': '2', 'x-ratelimit-reset-tokens': '5s',
                                      'x-ratelimit-reset-requests': '1h', 'x-ratelimit-remaining-requests': '900'})
        self.assertEqual(client.retry_delay(response, 0), 6)

    def test_nested_retries_share_one_http_budget(self):
        with patch.object(client.time, 'sleep'), patch.object(client.requests, 'post', return_value=reply()) as post:
            with budget.request_budget(3):
                client.chat_json('first source')
                with budget.request_budget(2):
                    client.chat_json('editor')
                client.chat_json('second source')
                with self.assertRaises(budget.GroqBudgetError):
                    client.chat_json('no budget left')
            self.assertEqual(post.call_count, 3)
            # New runs get their own allowance.
            with budget.request_budget(1):
                client.chat_json('new run')
            self.assertEqual(post.call_count, 4)

    def test_transient_service_errors_have_at_most_three_attempts(self):
        with patch.object(client.time, 'sleep'), patch.object(client.requests, 'post', return_value=reply(503, text='{}')) as post:
            with self.assertRaises(requests.HTTPError):
                client.chat_json('source')
        self.assertEqual(post.call_count, 3)

    def test_retries_also_consume_the_outer_budget(self):
        with budget.request_budget(2), patch.object(client.time, 'sleep'), \
             patch.object(client.requests, 'post', return_value=reply(503, text='{}')) as post:
            with self.assertRaises(budget.GroqBudgetError):
                client.chat_json('source')
        self.assertEqual(post.call_count, 2)

    def test_malformed_diagnostic_is_not_a_generation_error(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'diagnostic.json'
            for data in ('broken json', '[]', '{"not_before":"bad"}'):
                target.write_text(data)
                with self.subTest(data=data), patch.dict(os.environ, {'PUBLISH_UPLOAD_CHECKPOINTS': '1'}), \
                     patch.object(client, 'Path', return_value=target), patch.object(client.time, 'sleep'), \
                     patch.object(client.requests, 'post', return_value=reply()) as post:
                    self.assertEqual(client.chat_json('source'), {'ok': True})
                    self.assertEqual(post.call_count, 1)


if __name__ == '__main__':
    unittest.main()

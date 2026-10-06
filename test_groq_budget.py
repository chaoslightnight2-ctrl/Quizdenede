"""Completion exhaustion retries must keep the real model, source and schema."""
import copy
import json
import os
import types
import unittest
from unittest.mock import patch

try:
    import groq_client as client
except ModuleNotFoundError:
    from src import groq_client as client


class GroqCompletionBudgetTests(unittest.TestCase):
    def exercise(self, first_response, max_tokens=4096):
        requests_seen = []
        schema = client.object_schema({'ready': {'type': 'boolean'}})
        success = types.SimpleNamespace(status_code=200, headers={}, text='',
            json=lambda: {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ready":true}'}}]})
        replies = iter([first_response, success])

        def post(url, **kwargs):
            requests_seen.append((url, copy.deepcopy(kwargs['json'])))
            return next(replies)

        with patch.dict(os.environ, {'GROQ_API_KEY': 'unit-test', 'GROQ_MODEL': 'openai/gpt-oss-120b',
                                     'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(client.requests, 'post', side_effect=post), patch.object(client.time, 'sleep'):
            client._next_request = 0
            result = client.chat_json('SUPPLIED SOURCE: measured value is approximate', schema=schema, max_tokens=max_tokens)
        self.assertEqual(result, {'ready': True})
        self.assertEqual(len(requests_seen), 2)
        self.assertEqual(requests_seen[0][1]['max_completion_tokens'], max_tokens)
        self.assertGreaterEqual(requests_seen[1][1]['max_completion_tokens'], max_tokens)
        self.assertLessEqual(requests_seen[1][1]['max_completion_tokens'], 8192)
        for url, body in requests_seen:
            self.assertEqual(url, client.URL)
            self.assertEqual(body['model'], 'openai/gpt-oss-120b')
            self.assertEqual(body['reasoning_effort'], 'medium')
            self.assertEqual(body['response_format']['json_schema']['schema'], schema)
            self.assertIn('SUPPLIED SOURCE: measured value is approximate', body['messages'][-1]['content'])
        return requests_seen[1][1]['max_completion_tokens']

    def test_provider_json_failure_can_grow_past_old_4096_cap(self):
        failure = types.SimpleNamespace(status_code=400, headers={}, text='',
            json=lambda: {'error': {'code': 'json_validate_failed', 'message': 'Failed to generate JSON',
                                    'failed_generation': 'max completion tokens reached before generating a valid document'}})
        self.assertGreater(self.exercise(failure), 4096)

    def test_http_200_truncation_is_retried_without_accepting_partial_text(self):
        truncated = types.SimpleNamespace(status_code=200, headers={}, text='',
            json=lambda: {'choices': [{'finish_reason': 'length', 'message': {'content': '{"ready":'}}]})
        self.assertGreater(self.exercise(truncated), 4096)

    def test_provider_json_retry_budget_remains_bounded(self):
        failure = types.SimpleNamespace(status_code=400, headers={}, text='',
            json=lambda: {'error': {'code': 'json_validate_failed', 'message': 'Failed to generate JSON',
                                    'failed_generation': 'max completion tokens reached before generating a valid document'}})
        self.assertEqual(self.exercise(failure, max_tokens=8192), 8192)


if __name__ == '__main__':
    unittest.main()

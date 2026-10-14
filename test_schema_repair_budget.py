import copy
import os
import types
import unittest
from unittest.mock import patch
try:
    from src import groq_client
except ImportError:
    import groq_client


class SchemaRepairBudgetTests(unittest.TestCase):
    def test_complete_wrong_enum_does_not_inflate_the_quota_reservation(self):
        bodies = []
        def post(*args, **kwargs):
            bodies.append(copy.deepcopy(kwargs['json']))
            if len(bodies) == 1:
                return types.SimpleNamespace(status_code=400, headers={}, text='', json=lambda: {'error': {
                    'code': 'json_validate_failed', 'message': 'JSON schema enum value mismatch',
                    'failed_generation': '{"mode":"wrong"}'}})
            return types.SimpleNamespace(status_code=200, json=lambda: {'choices': [{
                'finish_reason': 'stop', 'message': {'content': '{"mode":"right"}'}}]})
        schema = groq_client.object_schema({'mode': {'type': 'string', 'enum': ['right']}})
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-only', 'PUBLISH_UPLOAD_CHECKPOINTS': '0'}), \
             patch.object(groq_client.requests, 'post', side_effect=post), \
             patch.object(groq_client.time, 'sleep'):
            result = groq_client.chat_json('unchanged real reference input', max_tokens=1600, schema=schema)
        self.assertEqual(result['mode'], 'right')
        self.assertEqual([body['max_completion_tokens'] for body in bodies], [1600, 1600])
        self.assertEqual(bodies[0]['model'], bodies[1]['model'])
        self.assertEqual(bodies[1]['response_format']['type'], 'json_schema')
        self.assertIn('unchanged real reference input', bodies[1]['messages'][-1]['content'])

"""Small same-model schema request; never logs the API credential."""
import json
import os
from pathlib import Path
import requests

key = os.environ['GROQ_API_KEY']
schema = {'type': 'object', 'properties': {'ready': {'type': 'boolean'}, 'visual_query': {'type': 'string'}},
          'required': ['ready', 'visual_query'], 'additionalProperties': False}
response = requests.post('https://api.groq.com/openai/v1/chat/completions',
    headers={'Authorization': f'Bearer {key}'}, timeout=90, json={
        'model': 'openai/gpt-oss-120b', 'messages': [{'role': 'user', 'content': 'Return ready true and visual_query moon surface space.'}],
        'max_completion_tokens': 256, 'reasoning_effort': 'low', 'temperature': 0,
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'provider_test', 'strict': True, 'schema': schema}}})
data = response.json()
report = {'http_status': response.status_code,
          'limits': {k: v for k, v in response.headers.items() if k.lower().startswith('x-ratelimit-') or k.lower() == 'retry-after'}}
if response.ok:
    report['usage'] = data.get('usage')
    report['result'] = json.loads(data['choices'][0]['message']['content'])
else:
    report['error'] = str(data.get('error', {}).get('message', 'No error message')).replace(key, '[redacted]')
Path('maintenance/groq-probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if response.ok else 1)

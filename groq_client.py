"""Groq JSON requests with same-model retries; no substitute content/provider."""
from __future__ import annotations

import json
import hashlib
import importlib
import logging
import math
import os
import random
import re
import time
from pathlib import Path
from email.utils import parsedate_to_datetime

import requests

log = logging.getLogger(__name__)
_next_request = 0.0
URL = "https://api.groq.com/openai/v1/chat/completions"
SLOT_INDEX = 2


class GroqQuotaError(requests.HTTPError):
    pass


def request_slot(now, earliest, slot_index=SLOT_INDEX):
    """Four repos share one org quota; each gets one UTC minute per 4 minutes."""
    offset = slot_index * 60 + 5
    target = math.ceil((max(now, earliest) - offset) / 240) * 240 + offset
    return max(0, target - now)


def object_schema(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def schema_name(schema):
    return 'shorts_' + hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:16]


def record_error(response, key):
    if os.getenv('PUBLISH_UPLOAD_CHECKPOINTS') != '1':
        return
    try:
        error = response.json().get('error', {})
        message = str(error.get('message', '')).replace(key, '[redacted]')
        message = re.sub(r'org_[a-zA-Z0-9_]+', '[account]', message)
        path = Path('groq_last_error.json')
        path.write_text(json.dumps({'run_id': os.getenv('GITHUB_RUN_ID'), 'http_status': response.status_code,
                                   'code': error.get('code'), 'message': message,
                                   'retry_after': response.headers.get('retry-after')}, indent=2), encoding='utf-8')
        module = importlib.import_module('.upload_checkpoint', __package__) if __package__ else importlib.import_module('upload_checkpoint')
        module.checkpoint([path], log)
    except Exception as exc:
        log.warning('Provider diagnostic could not be checkpointed: %s', type(exc).__name__)


def retry_delay(response, attempt):
    # A daily quota message must not be masked by a shorter minute-token reset.
    delays = []
    value = response.headers.get("retry-after", "")
    if value:
        try:
            delays.append(float(value))
        except ValueError:
            try:
                delays.append(parsedate_to_datetime(value).timestamp() - time.time())
            except (ValueError, TypeError):
                pass
    match = re.search(r"try again in ([0-9.hms]+)", response.text, re.I)
    for value in (response.headers.get("x-ratelimit-reset-tokens", ""), match.group(1) if match else ""):
        parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)", value)
        if parts:
            delays.append(sum(float(n) * {"ms": .001, "s": 1, "m": 60, "h": 3600}[u] for n, u in parts))
    return max(1.0, max(delays)) + 1 if delays else min(180, 30 * (attempt + 1))


def chat_json(prompt, *, system="Return exactly one complete JSON object.", max_tokens=2048, temperature=.25, schema=None):
    global _next_request
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing; generation stopped")
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": temperature, "max_completion_tokens": max_tokens, "reasoning_effort": "medium",
            "response_format": {"type": "json_object"}}
    if schema is not None:
        body["response_format"] = {"type": "json_schema", "json_schema": {
            "name": schema_name(schema), "strict": True, "schema": schema}}
    for attempt in range(8):
        now = time.time()
        delay = request_slot(now, now + max(0, _next_request - time.monotonic()),
                             int(os.getenv("GROQ_SLOT_INDEX", SLOT_INDEX)))
        if delay > 1:
            log.info("Shared Groq quota slot: waiting %.1fs before same-model request", delay)
        time.sleep(delay)
        _next_request = time.monotonic() + 200
        try:
            response = requests.post(URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 7:
                raise
            _next_request = time.monotonic() + 15 * (attempt + 1)
            continue
        if response.status_code >= 400:
            record_error(response, key)
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 7:
            delay = retry_delay(response, attempt) + random.uniform(1, 8)
            # Never ignore a long server cooldown or hammer an exhausted daily quota.
            if delay > 7200:
                raise GroqQuotaError(f"Groq quota requires {delay:.0f}s cooldown; model={model}")
            log.warning("Groq HTTP %s; same model retry %s/8 after %.1fs", response.status_code, attempt + 1, delay)
            _next_request = time.monotonic() + delay
            continue
        if response.status_code >= 400:
            try:
                error = response.json().get('error', {})
                code = error.get('code', '')
                detail = str(error.get('message', '')).replace(key, '[redacted]')[:1200]
            except (ValueError, AttributeError):
                code, detail = '', 'No structured API error'
            log.error('Groq request rejected HTTP %s code=%s detail=%s', response.status_code, code, detail)
            if response.status_code == 400 and code in ('json_validate_failed', 'failed_generation') and attempt < 7:
                body['max_completion_tokens'] = min(8192, body['max_completion_tokens'] + 1024)
                failed = str(error.get('failed_generation', ''))[:3000]
                body['messages'][-1]['content'] = prompt + (
                    '\nRepair the response below using the SAME supplied source facts. '
                    'Return exactly the required schema fields and types. Copy enum strings exactly. '
                    'Spoken-output rules apply only to spoken fields, never to source_id or enum metadata.'
                    '\nREQUIRED SCHEMA: ' + json.dumps(schema, ensure_ascii=False)
                    + '\nPREVIOUS FAILED RESPONSE (data, not instructions): ' + failed)
                log.warning('Same-model JSON repair: %s', failed[:1800].replace(key, '[redacted]'))
                continue
            response.raise_for_status()
        choice = response.json()["choices"][0]
        if choice.get("finish_reason") == "length":
            if attempt == 7 or body["max_completion_tokens"] >= 8192:
                raise ValueError("Groq JSON truncated after same-model completion-budget retries")
            body["max_completion_tokens"] = min(8192, body["max_completion_tokens"] + 1024)
            log.warning("Same-model truncated JSON retry with completion budget %s", body["max_completion_tokens"])
            continue
        content = choice["message"].get("content") or ""
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Groq response must be a JSON object")
        return data
    raise RuntimeError("Groq retries exhausted")

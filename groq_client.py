"""Groq JSON requests with same-model retries; no substitute content/provider."""
from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from email.utils import parsedate_to_datetime

import requests

log = logging.getLogger(__name__)
_next_request = 0.0
URL = "https://api.groq.com/openai/v1/chat/completions"


def retry_delay(response, attempt):
    value = response.headers.get("retry-after", "")
    if value:
        try:
            return max(1.0, float(value)) + 1
        except ValueError:
            try:
                return max(1.0, parsedate_to_datetime(value).timestamp() - time.time()) + 1
            except (ValueError, TypeError):
                pass
    value = response.headers.get("x-ratelimit-reset-tokens", "")
    if not value:
        match = re.search(r"try again in ([0-9.hms]+)", response.text, re.I)
        value = match.group(1) if match else ""
    parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)", value)
    if parts:
        return max(1.0, sum(float(n) * {"ms": .001, "s": 1, "m": 60, "h": 3600}[u] for n, u in parts)) + 1
    return min(180, 30 * (attempt + 1))


def chat_json(prompt, *, system="Return exactly one complete JSON object.", max_tokens=2048, temperature=.25):
    global _next_request
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing; generation stopped")
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": temperature, "max_completion_tokens": max_tokens, "reasoning_effort": "low",
            "response_format": {"type": "json_object"}}
    for attempt in range(8):
        time.sleep(max(0, _next_request - time.monotonic()))
        _next_request = time.monotonic() + 45
        try:
            response = requests.post(URL, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 7:
                raise
            _next_request = time.monotonic() + 15 * (attempt + 1)
            continue
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 7:
            delay = retry_delay(response, attempt) + random.uniform(1, 8)
            # Never ignore a long server cooldown or hammer an exhausted daily quota.
            if delay > 900:
                raise RuntimeError(f"Groq quota requires {delay:.0f}s cooldown; model={model}")
            log.warning("Groq HTTP %s; same model retry %s/8 after %.1fs", response.status_code, attempt + 1, delay)
            _next_request = time.monotonic() + delay
            continue
        response.raise_for_status()
        choice = response.json()["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError("Groq JSON truncated: shorten output or increase completion budget")
        content = choice["message"].get("content") or ""
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Groq response must be a JSON object")
        return data
    raise RuntimeError("Groq retries exhausted")

"""Bound actual HTTP attempts across nested generation and editorial retries."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import os
import requests


class GroqBudgetError(requests.RequestException):
    """Stop the current run; this is not a source or schema validation failure."""


_budgets = ContextVar('groq_request_budgets', default=())


@contextmanager
def request_budget(limit):
    limit = int(limit)
    if limit < 1:
        raise ValueError('Groq request budget must be positive')
    token = _budgets.set((*_budgets.get(), {'remaining': limit, 'limit': limit}))
    try:
        yield
    finally:
        _budgets.reset(token)


def consume_request():
    budgets = _budgets.get()
    if any(budget['remaining'] <= 0 for budget in budgets):
        raise GroqBudgetError('Groq HTTP attempt budget exhausted; resume in a later run')
    for budget in budgets:
        budget['remaining'] -= 1


def limited_requests(setting, default):
    """Callable defaults let bulk callers account for their requested item count."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            limit = os.getenv(setting)
            if limit is None:
                limit = default(*args, **kwargs) if callable(default) else default
            with request_budget(limit):
                return function(*args, **kwargs)
        return wrapped
    return decorate

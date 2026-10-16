"""Structural source coverage and immutable approval; not a truth oracle."""
import hashlib
import json

VERSION = 2


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def evidence_schema():
    row = {'type': 'object', 'properties': {
        'field': {'type': 'string'}, 'source_quote': {'type': 'string'},
        'supported': {'type': 'boolean'}},
        'required': ['field', 'source_quote', 'supported'], 'additionalProperties': False}
    return {'type': 'array', 'items': row}


def validate_review(review, fields, source):
    if not isinstance(review, dict) or review.get('valid') is not True:
        raise ValueError('Editorial approval missing or rejected')
    if not isinstance(fields, dict) or not fields or any(not isinstance(v, str) or not v.strip() for v in fields.values()):
        raise ValueError('Reviewed publication fields missing')
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Real source text missing')
    rows = review.get('evidence')
    if not isinstance(rows, list) or len(rows) != len(fields):
        raise ValueError('Every publication field needs its own source evidence')
    seen = set()
    source = ' '.join(source.split())
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid evidence row')
        field = row.get('field')
        if not isinstance(field, str) or field not in fields or field in seen:
            raise ValueError('Unknown or duplicate evidence field')
        quote = row.get('source_quote')
        quote = ' '.join(quote.split()) if isinstance(quote, str) else ''
        if row.get('supported') is not True or len(quote) < 12 or quote not in source:
            raise ValueError('Missing, unsupported or invented source evidence: ' + field)
        seen.add(field)


def make_proof(payload, fields, source, review):
    validate_review(review, fields, source)
    return {'version': VERSION, 'payload_digest': digest(payload), 'fields_digest': digest(fields),
            'source_digest': digest(source), 'review_digest': digest(review)}


def require_proof(payload, fields, source, review, proof):
    expected = make_proof(payload, fields, source, review)
    if not isinstance(proof, dict) or proof != expected:
        raise ValueError('Publication changed after review or has no current approval')


EVIDENCE_INSTRUCTIONS = (
    '\nHer DENETLENECEK_ALANLAR anahtarı için evidence listesinde tam bir satır ver. '
    'field anahtarı aynen kopyala source_quote ilgili iddiayı destekleyen gerçek '
    'kaynak pasajını aynen alıntılasın supported yalnızca anlam özne yer zaman sayı '
    'kapsam ve belirsizlik birlikte doğruysa true olsun. Başlık açıklama ve her '
    'anlatım cümlesini ayrı denetle. Kaynağa benzeyen sözcükler yeterli değildir. '
    'Bir alan bile desteklenmiyorsa valid=false ver. Eksik alıntıyı uydurma. '
    'Soru biçimindeki başlık da kaynakta yanıt bulmalı. Yeni model çağrısı isteme.\n'
)

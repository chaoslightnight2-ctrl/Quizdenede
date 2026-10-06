"""Send only the existing OAuth client configuration to the owner's ephemeral key."""
import base64
import json
import os
import re
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def envelope(config, public_der, repository, request_id):
    if not re.fullmatch(r'[a-f0-9]{32}', request_id):
        raise ValueError('Invalid request identifier')
    public = serialization.load_der_public_key(base64.b64decode(public_der, validate=True))
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 3072:
        raise ValueError('RSA recipient key must be at least 3072 bits')
    # No refresh token, Groq key or upload credentials enter this envelope.
    selected = next((key for key in ('installed', 'web') if key in config), None)
    if selected is None:
        raise ValueError('OAuth client configuration is missing')
    fields = ('client_id', 'client_secret', 'auth_uri', 'token_uri', 'redirect_uris', 'project_id')
    client = {key: config[selected][key] for key in fields if key in config[selected]}
    if not client.get('client_id') or not client.get('client_secret'):
        raise ValueError('OAuth client fields are missing')
    aad = f'{repository}:{request_id}'.encode()
    key, nonce = os.urandom(32), os.urandom(12)
    cipher = AESGCM(key).encrypt(nonce, json.dumps({selected: client}).encode(), aad)
    wrapped = public.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=aad))
    return {'version': 1, 'repository': repository, 'request_id': request_id,
            **{name: base64.b64encode(value).decode() for name, value in
               [('wrapped_key', wrapped), ('nonce', nonce), ('ciphertext', cipher)]}}

def main():
    config = json.loads(os.environ['CLIENT_SECRETS_JSON'])
    result = envelope(config, os.environ['RECIPIENT_PUBLIC_DER'], os.environ['GITHUB_REPOSITORY'], os.environ['REQUEST_ID'])
    Path('oauth-client-envelope.json').write_text(json.dumps(result), encoding='utf-8')
    print('OAuth client envelope ready; recipient private key is required.')

if __name__ == '__main__':
    main()

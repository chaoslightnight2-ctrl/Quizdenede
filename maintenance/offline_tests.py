"""Run repository tests with fake credentials and a network tripwire."""
import os
import sys
import unittest
import socket
from unittest.mock import patch

sys.path.insert(0, os.getcwd())
os.environ.update(GROQ_API_KEY='offline-test-only', PEXELS_API_KEY='offline-test-only',
                  YOUTUBE_REFRESH_TOKEN='offline-test-only', PUBLISH_UPLOAD_CHECKPOINTS='0',
                  GITHUB_EVENT_NAME='unit_test', IMAGEMAGICK_BINARY='auto-detect')
import requests

_connect = socket.socket.connect

def offline_connect(sock, address):
    # Windows asyncio creates its wakeup socket pair over loopback.
    if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1', 'localhost'):
        return _connect(sock, address)
    raise AssertionError('Unexpected external socket connection in offline tests')

with patch.object(requests.sessions.Session, 'request', side_effect=AssertionError('Unexpected network request in offline tests')), \
     patch.object(socket.socket, 'connect', new=offline_connect):
    suite = unittest.defaultTestLoader.discover('.', pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(not result.wasSuccessful())

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, AsyncMock
import edge_tts_healthcheck as probe


class ProbeRetryTests(unittest.TestCase):
    def test_transient_empty_audio_retries_same_voice_and_requires_word_times(self):
        calls = []
        class Stream:
            async def stream(self):
                if len(calls) == 1:
                    yield {'type': 'audio', 'data': b'partial'}
                    raise RuntimeError('temporary empty stream')
                yield {'type': 'audio', 'data': b'complete'}
                yield {'type': 'WordBoundary', 'text': 'Bu'}
        def factory(*args, **kwargs):
            calls.append((args, kwargs))
            return Stream()
        with TemporaryDirectory() as folder, patch.object(probe, 'OUT', Path(folder) / 'probe.mp3'), \
             patch.object(probe.edge_tts, 'Communicate', side_effect=factory), \
             patch.object(probe.asyncio, 'sleep', new=AsyncMock()), \
             patch.object(probe, 'apply_copied_patches', create=True):
            asyncio.run(probe.main())
            self.assertEqual(probe.OUT.read_bytes(), b'complete')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[0][1]['boundary'], 'WordBoundary')

    def test_persistent_failure_does_not_become_a_pass_or_leave_partial_audio(self):
        class Stream:
            async def stream(self):
                yield {'type': 'audio', 'data': b'partial'}
                raise RuntimeError('service failed')
        with TemporaryDirectory() as folder, patch.object(probe, 'OUT', Path(folder) / 'probe.mp3'), \
             patch.object(probe.edge_tts, 'Communicate', return_value=Stream()) as create, \
             patch.object(probe.asyncio, 'sleep', new=AsyncMock()), \
             patch.object(probe, 'apply_copied_patches', create=True) as apply:
            with self.assertRaisesRegex(RuntimeError, 'service failed'):
                asyncio.run(probe.main())
            self.assertFalse(probe.OUT.exists())
            self.assertEqual(create.call_count, 3)
            apply.assert_not_called()


if __name__ == '__main__':
    unittest.main()

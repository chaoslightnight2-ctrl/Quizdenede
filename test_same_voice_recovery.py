import asyncio
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
import voice_sync as voice
from edge_tts.exceptions import NoAudioReceived


class SameVoiceRecoveryTests(unittest.TestCase):
    def invoke(self, target):
        asyncio.run(voice.synthesize('Merhaba', target, types.SimpleNamespace(DEFAULT_VOICE='tr-TR-AhmetNeural', RATE='+0%', PITCH='-2Hz')))

    def test_service_can_recover_after_three_empty_turns_without_stale_audio(self):
        calls = []
        class Stream:
            async def stream(self):
                if len(calls) <= 3:
                    yield {'type': 'audio', 'data': b'partial'}
                    raise NoAudioReceived('upstream closed without complete audio')
                yield {'type': 'audio', 'data': b'complete'}
                yield {'type': 'WordBoundary', 'offset': 0, 'duration': 5000000, 'text': 'Merhaba'}
        def create(*args, **kwargs):
            calls.append((args, kwargs))
            return Stream()
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'audio.mp3'
            target.with_suffix('.words.json').write_text('stale')
            with patch.object(voice.edge_tts, 'Communicate', side_effect=create), patch.object(voice.asyncio, 'sleep', new=AsyncMock()) as wait:
                self.invoke(target)
            self.assertEqual(target.read_bytes(), b'complete')
            self.assertNotIn('stale', target.with_suffix('.words.json').read_text())
            self.assertEqual([c.args[0] for c in wait.await_args_list], [15, 30, 60])
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(call == calls[0] for call in calls))
        self.assertEqual(calls[0][1]['boundary'], 'WordBoundary')

    def test_failed_service_leaves_no_partial_audio_or_old_word_timings(self):
        class Stream:
            async def stream(self):
                yield {'type': 'audio', 'data': b'partial'}
                raise NoAudioReceived('upstream unavailable')
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'audio.mp3'
            target.with_suffix('.words.json').write_text('stale')
            with patch.object(voice.edge_tts, 'Communicate', return_value=Stream()) as create, patch.object(voice.asyncio, 'sleep', new=AsyncMock()):
                with self.assertRaises(RuntimeError):
                    self.invoke(target)
            self.assertEqual(create.call_count, 5)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.words.json').exists())

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from voice_sync import quiz_pause


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg unavailable')
class ThinkingPauseTests(unittest.TestCase):
    def test_three_seconds_follow_question_without_spoken_wait_announcement(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / 'voice.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=700:duration=1', '-f', 'lavfi', '-i',
                            'anullsrc=r=24000:cl=mono:d=0.5', '-f', 'lavfi', '-i',
                            'sine=frequency=700:duration=1', '-filter_complex',
                            '[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]', '-map', '[out]', str(audio)], check=True)
            rows = [(0, 1, 'Soru'), (1.5, .2, 'Doğru'), (1.7, .2, 'cevap')]
            adjusted = quiz_pause(audio, rows)
            self.assertAlmostEqual(adjusted[1][0] - sum(adjusted[0][:2]), 3, delta=.08)
            self.assertEqual([row[2] for row in adjusted], ['Soru', 'Doğru', 'cevap'])
            self.assertEqual(adjusted[0], rows[0])
            raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(audio),
                                           '-ac', '1', '-ar', '24000', '-f', 's16le', '-'])
            self.assertAlmostEqual(len(raw) / (24000 * 2), 5, delta=.15)

if __name__ == '__main__':
    unittest.main()

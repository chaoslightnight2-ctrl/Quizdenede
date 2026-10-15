import types
import unittest
from unittest.mock import Mock, patch
import quiz_presentation as presentation


class NativeQuizBackgroundTests(unittest.TestCase):
    def test_primary_quiz_design_does_not_search_for_stock(self):
        bot = types.SimpleNamespace(build_video_for_item=Mock(), assemble_video=Mock(),
                                    generate_captions=Mock(), chunk_timestamps=Mock(),
                                    download_background_video=Mock(side_effect=AssertionError('stock request')),
                                    VIDEO_SIZE=(1080, 1920))
        presentation.install(bot)
        with patch.object(presentation, 'write_quiz_background') as write:
            bot.download_background_video({'question_text': 'Gerçek soru'}, 'background.mp4')
        write.assert_called_once_with('background.mp4', (1080, 1920))

    def test_native_frame_is_portrait_and_has_a_legible_dark_question_area(self):
        frame = presentation.quiz_background_frame(108, 192)
        self.assertEqual(frame.shape, (192, 108, 3))
        self.assertEqual(str(frame.dtype), 'uint8')
        self.assertLess(int(frame.max()), 100)


if __name__ == '__main__':
    unittest.main()

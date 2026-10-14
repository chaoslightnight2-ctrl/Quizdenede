import unittest
from unittest.mock import patch
try:
    from src import stock_relevance as stock, groq_client
except ImportError:
    import stock_relevance as stock
    import groq_client


class StockSelectionTests(unittest.TestCase):
    def test_real_metadata_selection_never_calls_groq(self):
        weak = {'id': 1, 'url': 'https://www.pexels.com/video/person-walking-1/'}
        best = {'id': 2, 'url': 'https://www.pexels.com/video/person-using-tablet-2/'}
        with patch.object(groq_client, 'chat_json', side_effect=AssertionError('clip LLM call')) as generate:
            self.assertEqual(stock.select_assets([{'query': 'person tablet', 'assets': [weak, best]}]), [best])
        generate.assert_not_called()

    def test_unfinished_screen_is_excluded(self):
        unfinished = {'id': 9, 'url': 'https://www.pexels.com/video/tablet-with-green-screen-9/'}
        real = {'id': 10, 'url': 'https://www.pexels.com/video/person-using-tablet-10/'}
        self.assertEqual(stock.select_assets([{'query': 'person tablet', 'assets': [unfinished, real]}]), [real])

    def test_natural_green_subject_remains_eligible(self):
        leaves = {'id': 11, 'url': 'https://www.pexels.com/video/green-leaves-in-forest-11/'}
        self.assertGreater(stock.relevance('green forest leaves', leaves), 0)

    def test_zero_match_is_not_a_random_substitute(self):
        rabbit = {'id': 1, 'url': 'https://www.pexels.com/video/girl-petting-rabbit-1/'}
        with self.assertRaisesRegex(ValueError, 'No described asset'):
            stock.select_assets([{'query': 'planet solar system', 'assets': [rabbit]}])

    def test_scene_order_and_actual_assets_are_preserved(self):
        lab = {'id': 3, 'url': 'https://www.pexels.com/video/researcher-in-lab-3/'}
        sea = {'id': 4, 'url': 'https://www.pexels.com/video/ocean-waves-4/'}
        self.assertEqual(stock.select_assets([
            {'query': 'scientist laboratory research', 'assets': [sea, lab]},
            {'query': 'ocean surface waves', 'assets': [lab, sea]}]), [lab, sea])

    def test_query_text_is_not_asset_evidence(self):
        asset = {'id': 3, 'url': 'https://www.pexels.com/video/walking-person-3/', 'query': 'planet solar system'}
        with self.assertRaises(ValueError):
            stock.select_assets([{'query': 'planet solar system', 'assets': [asset]}])


if __name__ == '__main__':
    unittest.main()

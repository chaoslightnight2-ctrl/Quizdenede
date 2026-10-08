import unittest
from unittest.mock import patch
try:
    from src import stock_relevance as stock
except ImportError:
    import stock_relevance as stock


class StockSelectionTests(unittest.TestCase):
    def test_zero_match_cannot_be_selected_even_if_it_is_the_only_clip(self):
        rabbit = {'id': 1, 'url': 'https://www.pexels.com/video/girl-petting-rabbit-1/'}
        with patch.object(stock, 'chat_json') as generate:
            with self.assertRaisesRegex(ValueError, 'No described asset'):
                stock.select_assets([{'query': 'planet solar system', 'assets': [rabbit]}])
        generate.assert_not_called()

    def test_shared_word_does_not_override_scene_mismatch(self):
        hugging = {'id': 2, 'url': 'https://www.pexels.com/video/army-soldier-hugging-family-2/'}
        with patch.object(stock, 'chat_json', return_value={'selections': [
                {'scene_id': '0', 'asset_id': '', 'reason': 'Domestic reunion does not show a defense pact'}]}):
            with self.assertRaisesRegex(ValueError, 'No relevant stock'):
                stock.select_assets([{'query': 'military defense agreement',
                                      'text': 'Ülkeler ortak savunma anlaşması imzaladı', 'assets': [hugging]}])

    def test_all_scenes_use_their_actual_offered_assets(self):
        lab = {'id': 3, 'url': 'https://www.pexels.com/video/researcher-in-lab-3/'}
        sea = {'id': 4, 'url': 'https://www.pexels.com/video/ocean-waves-4/'}
        rows = [{'query': 'scientist laboratory research', 'assets': [lab]},
                {'query': 'ocean surface waves', 'assets': [sea]}]
        with patch.object(stock, 'chat_json', return_value={'selections': [
                {'scene_id': '1', 'asset_id': '4', 'reason': 'waves'},
                {'scene_id': '0', 'asset_id': '3', 'reason': 'laboratory'}]}):
            self.assertEqual(stock.select_assets(rows), [lab, sea])

    def test_unknown_id_or_missing_scene_never_becomes_a_random_clip(self):
        lab = {'id': 3, 'url': 'https://www.pexels.com/video/lab-research-3/'}
        for answer in ({'selections': []}, {'selections': [{'scene_id': '0', 'asset_id': '99', 'reason': 'invented'}]}):
            with patch.object(stock, 'chat_json', return_value=answer), self.assertRaises(ValueError):
                stock.select_assets([{'query': 'lab research', 'assets': [lab]}])

if __name__ == '__main__':
    unittest.main()

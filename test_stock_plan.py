import copy
import unittest
from unittest.mock import patch

try:
    from src import stock_plan as plan, stock_relevance as stock
except ImportError:
    import stock_plan as plan
    import stock_relevance as stock


class VisualPlanRepairTests(unittest.TestCase):
    def test_repair_changes_only_search_and_selected_asset_is_still_checked(self):
        scenes = [{'query': 'microscopic cell types', 'text': 'Bilim insanı hücreleri mikroskopla inceliyor'}]
        original = copy.deepcopy(scenes)
        microscope = {'id': 8, 'url': 'https://www.pexels.com/video/microscope-lab-experiment-8/'}
        searches = []
        def fetch(query):
            searches.append(query)
            return [microscope] if query == 'microscope lab experiment' else []
        with patch.object(plan, 'chat_json', return_value={'queries': [
                {'scene_id': '0', 'query': 'microscope lab experiment'}]}) as repair, \
             patch.object(stock, 'chat_json', return_value={'selections': [
                {'scene_id': '0', 'asset_id': '8', 'reason': 'microscope'}]}):
            selected, queries = plan.select_with_query_repair(scenes, fetch)
        self.assertEqual(scenes, original)
        self.assertEqual(selected, [microscope])
        self.assertEqual(queries, ['microscope lab experiment'])
        self.assertEqual(searches, ['microscopic cell types', 'microscope lab experiment'])
        self.assertEqual(repair.call_count, 1)

    def test_repeated_rejected_query_stops_instead_of_looping(self):
        with patch.object(plan, 'chat_json', return_value={'queries': [
                {'scene_id': '0', 'query': 'microscope lab experiment'}]}):
            with self.assertRaisesRegex(ValueError, 'did not repair'):
                plan.select_with_query_repair([{'query': 'microscope lab experiment'}], lambda _: [])

    def test_empty_stock_after_two_repairs_remains_a_failure(self):
        answers = [{'queries': [{'scene_id': '0', 'query': query}]}
                   for query in ('microscope science lab', 'microscope lab experiment')]
        with patch.object(plan, 'chat_json', side_effect=answers) as repair:
            with self.assertRaisesRegex(ValueError, 'No described asset'):
                plan.select_with_query_repair([{'query': 'microscopic cell types'}], lambda _: [])
        self.assertEqual(repair.call_count, 2)

    def test_repair_cannot_omit_or_invent_a_scene(self):
        for answer in ({'queries': []}, {'queries': [{'scene_id': '9', 'query': 'microscope science lab'}]}):
            with patch.object(plan, 'chat_json', return_value=answer):
                with self.assertRaises(ValueError):
                    plan.select_with_query_repair([{'query': 'microscopic cell types'}], lambda _: [])

if __name__ == '__main__':
    unittest.main()

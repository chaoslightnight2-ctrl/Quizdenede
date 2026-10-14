import copy
import unittest
from unittest.mock import patch
try:
    from src import stock_plan as plan, groq_client
except ImportError:
    import stock_plan as plan
    import groq_client


class VisualPlanRepairTests(unittest.TestCase):
    def test_clip_fetch_and_selection_make_zero_model_calls(self):
        asset = {'id': 8, 'url': 'https://www.pexels.com/video/microscope-lab-experiment-8/'}
        scenes = [{'query': 'microscope lab experiment', 'text': 'Hücreler inceleniyor', 'context': 'Biyoloji'}]
        original = copy.deepcopy(scenes)
        with patch.object(groq_client, 'chat_json', side_effect=AssertionError('clip LLM call')) as generate, \
             patch.object(plan, 'select_assets', wraps=plan.select_assets) as select:
            selected, queries = plan.select_with_query_repair(scenes, lambda _: [asset])
        generate.assert_not_called()
        self.assertEqual(selected, [asset])
        self.assertEqual(queries, [scenes[0]['query']])
        self.assertEqual(scenes, original)
        self.assertEqual(select.call_args.args[0][0]['context'], 'Biyoloji')

    def test_missing_clip_does_not_start_paid_query_repairs(self):
        queries = []
        def fetch(query):
            queries.append(query)
            return []
        with patch.object(groq_client, 'chat_json', side_effect=AssertionError('clip LLM call')) as generate:
            with self.assertRaisesRegex(ValueError, 'No described asset'):
                plan.select_with_query_repair([{'query': 'microscope science lab'}], fetch)
        generate.assert_not_called()
        self.assertEqual(queries, ['microscope science lab'])

    def test_search_error_is_not_hidden(self):
        def fetch(_):
            raise RuntimeError('Pexels unavailable')
        with self.assertRaisesRegex(RuntimeError, 'Pexels unavailable'):
            plan.select_with_query_repair([{'query': 'ocean waves'}], fetch)

    def test_each_original_query_is_used_once(self):
        assets = {'ocean waves': {'id': 1, 'url': 'https://www.pexels.com/video/ocean-waves-1/'},
                  'forest trees': {'id': 2, 'url': 'https://www.pexels.com/video/forest-trees-2/'}}
        queries = []
        def fetch(query):
            queries.append(query)
            return [assets[query]]
        selected, used = plan.select_with_query_repair([{'query': q} for q in assets], fetch)
        self.assertEqual(queries, list(assets))
        self.assertEqual(used, queries)
        self.assertEqual(selected, list(assets.values()))


if __name__ == '__main__':
    unittest.main()

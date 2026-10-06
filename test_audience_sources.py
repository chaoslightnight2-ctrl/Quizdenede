import unittest
from unittest.mock import patch, Mock
import knowledge_sources as sources

class AudienceSourcesTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch.object(sources.time, 'sleep')
        self.sleep.start()
        sources._page_cycles.clear()

    def tearDown(self):
        sources.fetch_sources.cache_clear()
        self.sleep.stop()

    def test_real_search_sources_replace_random_pool(self):
        pages = [{'pageid': i, 'title': f'Real article {i}', 'fullurl': f'https://en.wikipedia.org/wiki/{i}', 'extract': ' '.join(['live reference context'] * 40)} for i in range(6)]
        with patch.object(sources.requests, 'get', return_value=Mock(json=lambda: {'query': {'pages': pages}})) as request:
            rows = sources.fetch_sources('Psikoloji ve insan davranışları')
        self.assertEqual(len(rows), 6)
        params = request.call_args.kwargs['params']
        self.assertEqual(params['generator'], 'search')
        self.assertIn(params['gsrsearch'], [sources.search_query(term) for term in sources.DOMAINS['behavior']])
        self.assertTrue(all(row['text'].startswith('live reference') for row in rows))

    def test_empty_live_pool_produces_no_substitute(self):
        with patch.object(sources.requests, 'get', return_value=Mock(json=lambda: {'query': {'pages': []}})), self.assertRaisesRegex(RuntimeError, 'insufficient'):
            sources.fetch_sources('Teknoloji ve icatlar')

    def test_domain_coverage_without_specific_fact_templates(self):
        self.assertEqual(set(sources.search_terms('Teknoloji ve icatlar')), set(sources.DOMAINS['technology']))
        self.assertEqual(set(sources.search_terms('Günlük hayat ve eşyalar')), set(sources.DOMAINS['daily']))

    def test_each_domain_starts_with_relevant_first_page(self):
        pages = [{'pageid': i, 'title': f'Article {i}', 'fullurl': f'https://en.wikipedia.org/wiki/{i}', 'extract': ' '.join(['live context'] * 60)} for i in range(6)]
        with patch.object(sources.requests, 'get', return_value=Mock(json=lambda: {'query': {'pages': pages}})) as request:
            sources.fetch_sources('Günlük hayat ve eşyalar')
            sources.fetch_sources('Teknoloji ve icatlar')
        self.assertEqual([call.kwargs['params']['gsroffset'] for call in request.call_args_list], [0, 0])

    def test_rate_limit_waits_and_retries_identical_source_request(self):
        limited = Mock(status_code=429, headers={'Retry-After': '60'})
        success = Mock(status_code=200)
        with patch.object(sources.requests, 'get', side_effect=[limited, success]) as request, patch.object(sources.time, 'sleep') as sleep:
            self.assertIs(sources.request_page({'generator': 'search'}), success)
        self.assertIn(((60.0,), {}), [(call.args, call.kwargs) for call in sleep.call_args_list])
        self.assertEqual(request.call_args_list[0].kwargs['params'], request.call_args_list[1].kwargs['params'])

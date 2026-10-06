import unittest
from unittest.mock import patch, Mock
import knowledge_sources as sources

class AudienceSourcesTests(unittest.TestCase):
    def tearDown(self):
        sources.fetch_sources.cache_clear()

    def test_real_search_sources_replace_random_pool(self):
        pages = [{'pageid': i, 'title': f'Real article {i}', 'fullurl': f'https://en.wikipedia.org/wiki/{i}', 'extract': ' '.join(['live reference context'] * 40)} for i in range(6)]
        with patch.object(sources.requests, 'get', return_value=Mock(json=lambda: {'query': {'pages': pages}})) as request:
            rows = sources.fetch_sources('Psikoloji ve insan davranışları')
        self.assertEqual(len(rows), 6)
        params = request.call_args.kwargs['params']
        self.assertEqual(params['generator'], 'search')
        self.assertIn(params['gsrsearch'], sources.DOMAINS['behavior'])
        self.assertTrue(all(row['text'].startswith('live reference') for row in rows))

    def test_empty_live_pool_produces_no_substitute(self):
        with patch.object(sources.requests, 'get', return_value=Mock(json=lambda: {'query': {'pages': []}})), self.assertRaisesRegex(RuntimeError, 'insufficient'):
            sources.fetch_sources('Teknoloji ve icatlar')

    def test_domain_coverage_without_specific_fact_templates(self):
        self.assertEqual(set(sources.search_terms('Teknoloji ve icatlar')), set(sources.DOMAINS['technology']))
        self.assertEqual(set(sources.search_terms('Günlük hayat ve eşyalar')), set(sources.DOMAINS['daily']))

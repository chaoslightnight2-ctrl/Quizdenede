import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock
import audience_strategy as audience
import performance_feedback as feedback
import collect_performance as collector

class AudienceFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 6, tzinfo=timezone.utc)
        self.rows = [{'video_id': str(i), 'published_at': (self.now - timedelta(days=5)).isoformat(),
                     'engagedViews': 200, 'averageViewPercentage': 90 if i < 3 else 40,
                     'audience_bucket': 'daily_life' if i < 3 else 'culture',
                     'hook_style': 'direct_change' if i < 3 else 'concrete_question'} for i in range(6)]

    def test_target_audience_priorities(self):
        everyday = {'title': 'Türkiye konut kira ücretleri değişiyor'}
        celebrity = {'title': 'Foreign celebrity awards magazine'}
        self.assertGreater(audience.audience_score(everyday, 'Türkiye’den Haber'), audience.audience_score(celebrity, 'Türkiye’den Haber'))
        self.assertGreater(audience.audience_score({'title': 'Global energy fuel prices economy'}, 'Global Haber'), audience.audience_score(celebrity, 'Global Haber'))

    def test_sparse_missing_or_future_metrics_never_learn(self):
        self.assertEqual(feedback.learn(self.rows[:5], self.now)['status'], 'insufficient_data')
        self.rows[0]['published_at'] = (self.now + timedelta(days=1)).isoformat()
        self.assertEqual(feedback.learn(self.rows, self.now)['status'], 'insufficient_data')
        self.rows[0]['averageViewPercentage'] = None
        self.assertIsNone(feedback.number('NaN'))
        self.assertIsNone(feedback.number(''))

    def test_real_retention_and_swipe_feedback_is_bounded(self):
        for row in self.rows:
            row['stayed_to_watch_pct'] = 80 if row['audience_bucket'] == 'daily_life' else 20
            row['largest_drop_at_video_fraction'] = .1
            row['largest_drop_ratio'] = .12
        learned = feedback.learn(self.rows, self.now)
        self.assertGreater(learned['categories']['daily_life']['bonus'], 0)
        self.assertLess(learned['categories']['culture']['bonus'], 0)
        self.assertLessEqual(abs(learned['categories']['daily_life']['bonus']), 8)
        self.assertEqual(learned['pacing']['early_drop_videos'], 6)
        with patch.object(feedback, 'read_feedback', return_value=learned):
            self.assertIn('başlangıçta düşüş', feedback.prompt_feedback())

    def test_stale_or_inaccessible_report_not_applied(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'analytics.json'
            target.write_text(json.dumps({'status': 'ok', 'generated_at': '2020-01-01T00:00:00Z', 'learning': {'categories': {'daily_life': {'bonus': 8}}}}))
            with patch.object(feedback, 'REPORT', target):
                self.assertEqual(feedback.read_feedback(), {})

    def test_single_measured_hook_does_not_create_unmeasured_winner(self):
        with patch.object(feedback, 'read_feedback', return_value={'hook_styles': {'direct_change': {'bonus': 5}}}):
            self.assertEqual(feedback.choose_hook_style({'published': [{'hook_style': 'direct_change'}]}), 'concrete_question')

    def test_studio_missing_choice_is_not_zero(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / 'studio.csv'
            target.write_text('video_id,engagedViews,averageViewPercentage,stayed_to_watch_pct\n0,200,80,\n1,200,70,64\n', encoding='utf-8')
            rows = collector.read_studio_csv(target, self.rows)
            self.assertIsNone(rows[0]['stayed_to_watch_pct'])
            self.assertEqual(rows[1]['stayed_to_watch_pct'], 64)

    def test_api_does_not_infer_swipe_rate_and_queries_real_curve(self):
        session = Mock()
        session.headers = {}
        stats = {'columnHeaders': [{'name': k} for k in ['video', 'views', 'engagedViews', 'averageViewDuration', 'averageViewPercentage']], 'rows': [['0', 400, 200, 20, 80]]}
        curve = {'columnHeaders': [{'name': k} for k in ['elapsedVideoTimeRatio', 'audienceWatchRatio']], 'rows': [[.1, .9], [.2, .6]]}
        session.get.side_effect = [Mock(ok=True, json=lambda: stats), Mock(ok=True, json=lambda: curve)]
        env = {'CLIENT_SECRETS_JSON': json.dumps({'installed': {'client_id': 'test', 'client_secret': 'test-secret'}}), 'YOUTUBE_REFRESH_TOKEN': 'test-refresh'}
        import os
        with patch.dict(os.environ, env), patch.object(collector.requests, 'post', return_value=Mock(ok=True, json=lambda: {'access_token': 'test-access'})), patch.object(collector.requests, 'Session', return_value=session):
            rows = collector.read_api(self.rows, self.now)
        self.assertIsNone(rows[0]['stayed_to_watch_pct'])
        self.assertAlmostEqual(rows[0]['largest_drop_ratio'], .3)
        self.assertEqual(session.get.call_args.kwargs['params']['filters'], 'video==0')

    def test_scope_error_is_visible_without_secrets(self):
        session = Mock()
        session.headers = {}
        session.get.return_value = Mock(ok=False, status_code=403, headers={'content-type': 'application/json'}, json=lambda: {'error': {'errors': [{'reason': 'insufficientPermissions'}]}})
        env = {'CLIENT_SECRETS_JSON': json.dumps({'installed': {'client_id': 'test', 'client_secret': 'test-secret'}}), 'YOUTUBE_REFRESH_TOKEN': 'test-refresh'}
        import os
        with patch.dict(os.environ, env), patch.object(collector.requests, 'post', return_value=Mock(ok=True, json=lambda: {'access_token': 'test-access'})), patch.object(collector.requests, 'Session', return_value=session):
            with self.assertRaisesRegex(collector.AnalyticsUnavailable, 'analytics_403_insufficientPermissions'):
                collector.read_api(self.rows, self.now)

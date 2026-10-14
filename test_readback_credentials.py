import ast
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


class ReadbackCredentialTests(unittest.TestCase):
    def load(self):
        path = Path('maintenance/verify_existing_uploads.py')
        if not path.is_file():
            path = Path('../maintenance/verify_existing_uploads.py')
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'youtube_service')
        credentials, service = Mock(), Mock()
        service.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': 'intended'}]}
        constructor = Mock(return_value=credentials)
        namespace = {'json': json, 'os': os, 'Credentials': constructor, 'Request': Mock(),
                     'build': Mock(return_value=service), 'CHANNELS': {'example': 'intended'}}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
        return namespace['youtube_service'], constructor, service

    def env(self, read=True):
        config = lambda client: json.dumps({'installed': {'client_id': client, 'client_secret': 'test-only'}})
        return {'GITHUB_REPOSITORY': 'owner/example', 'CLIENT_SECRETS_JSON': config('upload-client'),
                'YOUTUBE_REFRESH_TOKEN': 'upload-test-token',
                'YOUTUBE_ANALYTICS_CLIENT_SECRETS_JSON': config('read-client') if read else '',
                'YOUTUBE_ANALYTICS_REFRESH_TOKEN': 'read-test-token' if read else ''}

    def test_existing_read_grant_is_used_only_for_status_reads(self):
        load, constructor, service = self.load()
        with patch.dict(os.environ, self.env(), clear=True):
            self.assertIs(load(), service)
        self.assertEqual(constructor.call_args.kwargs['client_id'], 'read-client')
        self.assertEqual(constructor.call_args.kwargs['refresh_token'], 'read-test-token')
        service.channels.return_value.list.assert_called_once_with(part='id', mine=True)
        service.videos.return_value.insert.assert_not_called()

    def test_wrong_channel_read_grant_is_not_accepted(self):
        load, _, service = self.load()
        service.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': 'other'}]}
        with patch.dict(os.environ, self.env(), clear=True), self.assertRaisesRegex(ValueError, 'intended channel'):
            load()

    def test_channel_without_read_grant_keeps_its_upload_credentials(self):
        load, constructor, service = self.load()
        with patch.dict(os.environ, self.env(read=False), clear=True):
            load()
        self.assertEqual(constructor.call_args.kwargs['client_id'], 'upload-client')
        service.channels.assert_not_called()

    def test_actual_public_status_is_proof_even_when_rss_is_unavailable(self):
        import importlib.util
        import tempfile
        path = Path('maintenance/verify_existing_uploads.py').resolve()
        if not path.is_file():
            path = Path('../maintenance/verify_existing_uploads.py').resolve()
        spec = importlib.util.spec_from_file_location('actual_readback_test', path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        service = Mock()
        service.videos.return_value.list.return_value.execute.return_value = {'items': [{
            'status': {'privacyStatus': 'public', 'uploadStatus': 'processed'},
            'processingDetails': {'processingStatus': 'succeeded'}, 'snippet': {'title': 'Actual title'}}]}
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'run_report.json').write_text(json.dumps({'run_id': '42', 'target_count': 1, 'videos': [{
                'video_id': 'AbcDef_0000', 'index': 1, 'publish_at_utc': '2050-01-01T00:00:00Z'}]}))
            (root / 'short_1.mp4').write_bytes(b'test-only-render')
            try:
                os.chdir(root)
                with patch('sys.argv', ['verify', '--source-run', '42', '--artifact-dir', str(root)]), \
                     patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(root / 'summary.md')}), \
                     patch.object(verifier, 'youtube_service', return_value=service), \
                     patch.object(verifier, 'public_listing', side_effect=RuntimeError('RSS unavailable')), \
                     patch.object(verifier, 'inspect_media', return_value={'duration': 30}), \
                     patch.object(verifier.subprocess, 'run'):
                    verifier.main()
                report = json.loads((root / 'maintenance/latest-verification.json').read_text())
            finally:
                os.chdir(previous)
        self.assertEqual(report['published_count'], 1)
        self.assertEqual(report['processed_count'], 1)
        self.assertTrue(report['complete'])
        self.assertEqual(report['videos'][0]['publication_status'], 'public_verified')

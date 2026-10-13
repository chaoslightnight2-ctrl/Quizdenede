from pathlib import Path
import tempfile
import os
import json
import unittest
from unittest.mock import patch

try:
    from src import upload_recovery as recovery
except ImportError:
    import upload_recovery as recovery


class RecoveryRequestTests(unittest.TestCase):
    def check(self, name, changed, config):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            request = root / recovery.REQUEST
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps(config), encoding='utf-8')
            event = root / 'event.json'
            event.write_text(json.dumps({'commits': [{'added': changed, 'modified': []}]}), encoding='utf-8')
            with patch.object(recovery, '__file__', str(root / 'upload_recovery.py')), \
                 patch.dict(os.environ, {'GITHUB_EVENT_NAME': name, 'GITHUB_EVENT_PATH': str(event)}):
                return recovery.requested()

    def test_only_explicit_request_push_enables_one_private_upload(self):
        self.assertTrue(self.check('push', [recovery.REQUEST],
                                   {'mode': 'verify_one_private_upload', 'enabled': True}))

    def test_schedule_and_manual_workflow_dispatch_keep_daily_mode(self):
        for event in ('schedule', 'workflow_dispatch'):
            self.assertFalse(self.check(event, [recovery.REQUEST],
                                        {'mode': 'verify_one_private_upload', 'enabled': True}))

    def test_other_commits_or_disabled_request_cannot_enable_recovery(self):
        config = {'mode': 'verify_one_private_upload', 'enabled': True}
        self.assertFalse(self.check('push', ['run_report.json'], config))
        self.assertFalse(self.check('push', [recovery.REQUEST], {**config, 'enabled': False}))
        self.assertFalse(self.check('push', [recovery.REQUEST], {**config, 'mode': 'other'}))

if __name__ == '__main__':
    unittest.main()

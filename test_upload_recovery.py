import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
try:
    from src import upload_recovery as recovery, upload_checkpoint as state
except ImportError:
    import upload_recovery as recovery, upload_checkpoint as state


class RealGitStateTests(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.run(['git', '-C', str(cwd), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def init(self, folder):
        remote = Path(folder) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        root = Path(folder) / 'runner'
        subprocess.run(['git', 'clone', str(remote), str(root)], check=True, capture_output=True)
        self.git(root, 'config', 'user.name', 'Test')
        self.git(root, 'config', 'user.email', 'test@example.invalid')
        self.git(root, 'checkout', '-b', 'main')
        (root / 'code.py').write_text('original code')
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-m', 'base')
        self.git(root, 'push', '-u', 'origin', 'main')
        return root, remote

    def test_real_actions_payload_without_changed_file_arrays(self):
        with tempfile.TemporaryDirectory() as folder:
            root, remote = self.init(folder)
            before = self.git(root, 'rev-parse', 'HEAD')
            request = root / recovery.REQUEST
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'enabled': True, 'mode': 'verify_one_private_upload'}))
            self.git(root, 'add', '.')
            self.git(root, 'commit', '-m', 'explicit recovery')
            after = self.git(root, 'rev-parse', 'HEAD')
            self.git(root, 'push', 'origin', 'main')
            shallow = Path(folder) / 'shallow'
            subprocess.run(['git', 'clone', '--depth=1', '--branch=main', remote.as_uri(), str(shallow)],
                           check=True, capture_output=True)
            event = Path(folder) / 'event.json'
            event.write_text(json.dumps({'before': before, 'after': after, 'commits': [{'id': after}]}))
            with patch.object(recovery, '__file__', str(shallow / 'upload_recovery.py')), \
                 patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push', 'GITHUB_EVENT_PATH': str(event)}):
                self.assertTrue(recovery.requested())
                self.assertEqual(self.git(shallow, 'rev-parse', 'HEAD'), after)
                with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule'}):
                    self.assertFalse(recovery.requested())
            # A later ordinary push must not inherit the enabled request file.
            (root / 'code.py').write_text('new code')
            self.git(root, 'add', '.')
            self.git(root, 'commit', '-m', 'ordinary code')
            other = self.git(root, 'rev-parse', 'HEAD')
            event.write_text(json.dumps({'before': after, 'after': other}))
            with patch.object(recovery, '__file__', str(root / 'upload_recovery.py')), \
                 patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push', 'GITHUB_EVENT_PATH': str(event)}):
                self.assertFalse(recovery.requested())

    def test_checkpoint_preserves_concurrent_code_ids_index_and_dirty_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root, remote = self.init(folder)
            history = root / 'history.json'
            history.write_text(json.dumps({'processed_news': [{'video_id': 'old', 'fingerprint': 'a'}]}))
            manifest = root / 'daily_manifest.json'
            manifest.write_text(json.dumps([{'run_id': 'old-run', 'video_id': 'old'}]))
            report = root / 'latest-verification.json'
            report.write_text(json.dumps({'source_run': 'old-run', 'accepted_count': 2,
                                          'videos': [{'video_id': 'old'}, {'video_id': 'peer'}]}))
            self.git(root, 'add', '.')
            self.git(root, 'commit', '-m', 'history')
            self.git(root, 'push', 'origin', 'main')
            head = self.git(root, 'rev-parse', 'HEAD')
            peer = Path(folder) / 'peer'
            subprocess.run(['git', 'clone', '--branch=main', str(remote), str(peer)], check=True, capture_output=True)
            self.git(peer, 'config', 'user.name', 'Test')
            self.git(peer, 'config', 'user.email', 'test@example.invalid')
            (peer / 'code.py').write_text('concurrent fix')
            (peer / 'history.json').write_text(json.dumps({'processed_news': [
                {'video_id': 'old', 'fingerprint': 'a'}, {'video_id': 'peer', 'fingerprint': 'b'}]}))
            self.git(peer, 'add', '.')
            self.git(peer, 'commit', '-m', 'concurrent fixes and receipt')
            self.git(peer, 'push', 'origin', 'main')
            history.write_text(json.dumps({'processed_news': [
                {'video_id': 'old', 'fingerprint': 'a'}, {'video_id': 'new', 'fingerprint': 'c'}]}))
            manifest.write_text(json.dumps([{'run_id': 'new-run', 'video_id': 'new'}]))
            report.write_text(json.dumps({'source_run': 'new-run', 'accepted_count': 1,
                                          'videos': [{'video_id': 'new'}]}))
            (root / 'dirty.txt').write_text('never staged or replaced')
            dirty = self.git(root, 'status', '--porcelain')
            previous = Path.cwd()
            try:
                nested = root / 'freefaceless'
                nested.mkdir()
                os.chdir(nested)
                with patch.dict(os.environ, {'PUBLISH_UPLOAD_CHECKPOINTS': '1'}):
                    self.assertTrue(state.checkpoint([history, manifest, report]))
            finally:
                os.chdir(previous)
            self.assertEqual(self.git(root, 'rev-parse', 'HEAD'), head)
            self.assertEqual(self.git(root, 'status', '--porcelain'), dirty)
            self.assertEqual((root / 'code.py').read_text(), 'original code')
            self.git(peer, 'pull', '--ff-only')
            self.assertEqual((peer / 'code.py').read_text(), 'concurrent fix')
            rows = json.loads((peer / 'history.json').read_text())['processed_news']
            self.assertEqual({r['video_id'] for r in rows}, {'old', 'peer', 'new'})
            self.assertEqual(json.loads((peer / 'daily_manifest.json').read_text()),
                             [{'run_id': 'new-run', 'video_id': 'new'}])
            verification = json.loads((peer / 'latest-verification.json').read_text())
            self.assertEqual(verification['accepted_count'], len(verification['videos']))
            self.assertEqual(verification['videos'], [{'video_id': 'new'}])

    def test_invalid_conflicted_json_is_not_committed(self):
        with tempfile.TemporaryDirectory() as folder:
            root, _ = self.init(folder)
            bad = root / 'run_report.json'
            bad.write_text('<<<<<<< Updated upstream\n{}\n=======\n{}\n>>>>>>> Stashed changes')
            head = self.git(root, 'rev-parse', 'HEAD')
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {'PUBLISH_UPLOAD_CHECKPOINTS': '1'}):
                    self.assertFalse(state.checkpoint([bad]))
            finally:
                os.chdir(previous)
            self.assertEqual(self.git(root, 'rev-parse', 'HEAD'), head)


if __name__ == '__main__':
    unittest.main()

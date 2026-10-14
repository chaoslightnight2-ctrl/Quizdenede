"""Recognize the explicit request from the actual Actions push commit range."""
import json
import os
import re
import subprocess
from pathlib import Path

REQUEST = '.github/maintenance/run-upload-recovery.json'


def requested():
    if os.getenv('GITHUB_EVENT_NAME') != 'push':
        return False
    root = Path(__file__).resolve().parent
    while not (root / '.github').is_dir() and root != root.parent:
        root = root.parent
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    config_path = root / REQUEST
    if not config_path.is_file():
        return False
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if config.get('mode') != 'verify_one_private_upload' or config.get('enabled') is not True:
        return False
    # Actions deliberately omits commit added/modified arrays. Use the immutable
    # before/after commit IDs; fetching objects never modifies the working files.
    before, after = event.get('before', ''), event.get('after', '')
    if not all(re.fullmatch(r'[0-9a-f]{40}', value) for value in (before, after)):
        raise ValueError('Push commit range missing; refusing an unintended daily upload')
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True,
                              capture_output=True, text=True, timeout=90).stdout
    for sha in (before, after):
        if sha == '0' * 40:
            continue
        try:
            git('cat-file', '-e', sha + '^{commit}')
        except subprocess.CalledProcessError:
            git('fetch', '--no-tags', '--depth=1', 'origin', sha)
    if before == '0' * 40:
        changed = git('ls-tree', '-r', '--name-only', after).splitlines()
    else:
        changed = git('diff', '--name-only', before, after).splitlines()
    return REQUEST in changed

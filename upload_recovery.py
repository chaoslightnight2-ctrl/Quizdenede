"""One private upload only for an explicit recovery-request push."""
import json
import os
from pathlib import Path

REQUEST = '.github/maintenance/run-upload-recovery.json'


def requested():
    if os.getenv('GITHUB_EVENT_NAME') != 'push':
        return False
    root = Path(__file__).resolve().parent
    while not (root / '.github').is_dir() and root != root.parent:
        root = root.parent
    try:
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
        changes = [path for commit in event.get('commits', [])
                   for key in ('added', 'modified') for path in commit.get(key, [])]
        if REQUEST not in changes:
            return False
        config = json.loads((root / REQUEST).read_text(encoding='utf-8'))
        return config.get('mode') == 'verify_one_private_upload' and config.get('enabled') is True
    except (OSError, ValueError, KeyError, TypeError):
        return False

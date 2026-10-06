"""Preserve pipeline state, including upload receipts and provider diagnostics."""
from __future__ import annotations
import logging
import os
from pathlib import Path
import subprocess
import time


def checkpoint(paths, logger=None):
    if os.getenv('PUBLISH_UPLOAD_CHECKPOINTS') != '1':
        return
    logger = logger or logging.getLogger(__name__)
    paths = [str(p) for p in paths if Path(p).is_file()]
    if not paths:
        return
    try:
        def git(*args):
            return subprocess.run(['git', *args], check=True, capture_output=True, text=True, timeout=90)
        git('config', 'user.name', 'github-actions[bot]')
        git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
        git('add', '-f', '--', *paths)
        if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode == 0:
            return
        git('commit', '-m', 'Preserve pipeline state checkpoint [skip ci]')
        for attempt in range(3):
            try:
                git('pull', '--rebase', '--autostash', 'origin', 'main')
                git('push', 'origin', 'HEAD:main')
                logger.info('Pipeline state checkpoint published to GitHub: %s', ', '.join(paths))
                return
            except subprocess.SubprocessError:
                if attempt == 2:
                    raise
                time.sleep(5)
    except subprocess.SubprocessError as exc:
        # The upload ID remains in the local report and artifact. Never reinsert.
        logger.warning('Upload checkpoint could not be pushed: %s', type(exc).__name__)

"""Publish selected state on remote HEAD without changing the running checkout."""
from __future__ import annotations
import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import time


def merge_state(remote, local):
    if isinstance(remote, list) and isinstance(local, list):
        result = list(remote)
        for row in local:
            if isinstance(row, dict):
                key = next((key for key in ('video_id', 'fingerprint', 'id', 'ts') if row.get(key)), None)
                match = next((i for i, old in enumerate(result)
                              if isinstance(old, dict) and key and old.get(key) == row[key]), None)
                if match is not None:
                    result[match] = merge_state(result[match], row)
                    continue
            if row not in result:
                result.append(row)
        return result
    if isinstance(remote, dict) and isinstance(local, dict):
        # A report describes one run. IDs from earlier runs live in the history.
        if remote.get('run_id') and local.get('run_id') and remote['run_id'] != local['run_id']:
            return local
        result = dict(remote)
        for key, value in local.items():
            result[key] = merge_state(result[key], value) if key in result else value
        return result
    return local


def checkpoint(paths, logger=None):
    if os.getenv('PUBLISH_UPLOAD_CHECKPOINTS') != '1':
        return False
    logger = logger or logging.getLogger(__name__)
    root = None
    def git(*args, env=None, data=None):
        command = ['git'] + (['-C', str(root)] if root is not None else []) + list(args)
        return subprocess.run(command, check=True, capture_output=True,
                              input=data, env=env, timeout=90)
    try:
        root = Path(git('rev-parse', '--show-toplevel').stdout.decode().strip())
        files = {}
        selected = []
        for name in paths:
            candidate = Path(name).resolve()
            selected.extend(candidate.rglob('*') if candidate.is_dir() else [candidate])
        for path in selected:
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            value = path.read_bytes()
            if path.suffix == '.json':
                json.loads(value)  # Invalid/conflicted JSON is never published.
            files[relative] = value
        if not files:
            return False
        with tempfile.TemporaryDirectory(prefix='shorts-checkpoint-') as folder:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / 'index'),
                       GIT_AUTHOR_NAME='github-actions[bot]', GIT_COMMITTER_NAME='github-actions[bot]',
                       GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com',
                       GIT_COMMITTER_EMAIL='41898282+github-actions[bot]@users.noreply.github.com')
            for attempt in range(3):
                git('fetch', '--no-tags', 'origin', 'main')
                parent = git('rev-parse', 'FETCH_HEAD').stdout.decode().strip()
                git('read-tree', parent, env=env)
                for path, value in files.items():
                    if path.endswith('.json') and Path(path).name in ('news_history.json', 'state.json', 'history.json'):
                        old = subprocess.run(['git', '-C', str(root), 'show', parent + ':' + path], capture_output=True, timeout=90)
                        if old.returncode == 0:
                            value = (json.dumps(merge_state(json.loads(old.stdout), json.loads(value)),
                                                ensure_ascii=False, indent=2) + '\n').encode('utf-8')
                    blob = git('hash-object', '-w', '--stdin', data=value).stdout.decode().strip()
                    git('update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + path, env=env)
                tree = git('write-tree', env=env).stdout.decode().strip()
                if tree == git('rev-parse', parent + '^{tree}').stdout.decode().strip():
                    return True
                commit = git('commit-tree', tree, '-p', parent, '-m',
                             'Preserve pipeline state checkpoint [skip ci]', env=env).stdout.decode().strip()
                try:
                    git('push', 'origin', commit + ':refs/heads/main')
                    logger.info('Pipeline state checkpoint published without changing checkout: %s', ', '.join(files))
                    return True
                except subprocess.SubprocessError:
                    if attempt == 2:
                        raise
                    time.sleep(2)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        logger.warning('State checkpoint not published; local receipts retained: %s', type(exc).__name__)
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='+')
    args = parser.parse_args()
    os.environ['PUBLISH_UPLOAD_CHECKPOINTS'] = '1'
    raise SystemExit(0 if checkpoint(args.paths) else 1)

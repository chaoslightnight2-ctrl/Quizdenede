"""Exercise production Groq generation only; no audio, visuals, render or upload."""
import copy
import json
import os
import re
from pathlib import Path
import sys
import traceback
import time
from datetime import datetime, timezone

sys.path.insert(0, str(Path.cwd()))
os.environ.update(DRY_RUN='1', ENABLE_YOUTUBE_UPLOAD='0', PUBLISH_UPLOAD_CHECKPOINTS='0')
os.environ.setdefault('PEXELS_API_KEY', 'text_audit_no_visual_requests')
os.environ.setdefault('YOUTUBE_REFRESH_TOKEN', 'text_audit_upload_disabled')
out = Path('text-audit')
out.mkdir(exist_ok=True)
family = sys.argv[1]
report = {'family': family, 'run_id': os.getenv('GITHUB_RUN_ID'), 'commit': os.getenv('GITHUB_SHA'),
          'text_only': True, 'complete': False, 'raw_groq_responses': [], 'samples': [], 'errors': []}

def save():
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

def record_client(client):
    original_post = client.requests.post
    def diagnostic_post(*args, **kwargs):
        response = original_post(*args, **kwargs)
        if response.status_code == 429:
            error = response.json().get('error', {})
            message = str(error.get('message', ''))
            key = os.getenv('GROQ_API_KEY', '')
            if key:
                message = message.replace(key, '[redacted]')
            message = re.sub(r'org_[a-zA-Z0-9_]+', '[account]', message)
            report['provider_quota'] = {'http_status': 429, 'code': error.get('code'),
                'message': message, 'retry_after': response.headers.get('retry-after'),
                'reset_tokens': response.headers.get('x-ratelimit-reset-tokens')}
            save()
            # Diagnostic only: stop rather than wait hours. Production retry policy is unchanged.
            raise client.GroqQuotaError('Text audit stopped on real Groq HTTP429; provider cooldown is in report')
        return response
    client.requests.post = diagnostic_post
    original = client.chat_json
    def recorded(*args, **kwargs):
        result = original(*args, **kwargs)
        report['raw_groq_responses'].append(copy.deepcopy(result))
        save()
        return result
    client.chat_json = recorded

def blocked(*args, **kwargs):
    raise RuntimeError('Text-only audit must not create media or upload')

def record_references(module):
    original = module.fetch_sources
    def recorded():
        sources = original()
        report['reference_sources'] = copy.deepcopy(sources)
        save()
        return sources
    module.fetch_sources = recorded

save()
try:
    repo_root = Path.cwd().parent if (Path.cwd().parent / '.github').exists() else Path.cwd()
    deadlines = []
    for marker in (repo_root / '.github/maintenance').glob('text-audit-*.json'):
        setting = json.loads(marker.read_text(encoding='utf-8'))
        if setting.get('groq_not_before'):
            deadlines.append(datetime.fromisoformat(setting['groq_not_before'].replace('Z', '+00:00')))
    if deadlines:
        deadline = max(deadlines).astimezone(timezone.utc)
        remaining = max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
        report['groq_not_before'] = deadline.isoformat()
        save()
        if remaining:
            print(f'Respecting recorded Groq cooldown: waiting {remaining:.0f}s', flush=True)
            time.sleep(remaining)
    if family == 'denede':
        from src import groq_client
        record_client(groq_client)
        from src import knowledge_sources
        record_references(knowledge_sources)
        from src import script
        report['samples'].append(script.generate())
    elif family == 'quiz':
        import groq_client
        record_client(groq_client)
        import knowledge_sources
        record_references(knowledge_sources)
        import run_quiz_main as module
        bot = module.bot
        bot.build_video_for_item = bot.create_voiceover = bot.upload_to_youtube = blocked
        history = bot.load_json(bot.HISTORY_FILE, {'processed_news': [], 'processed_questions': []})
        candidates = module._generate_candidate_round(history)
        if not candidates:
            raise RuntimeError('No verified genuine Groq questions')
        for question in candidates:
            item = {'quiz': question, 'title': module.viral_title_for_quiz(question['question'], question['topic']),
                    'summary': question['explanation'], 'query': question['topic'], 'fingerprint': question['id']}
            item['script'] = bot.generate_news_script(item)
            report['samples'].append(item)
            save()
    else:
        import groq_client
        record_client(groq_client)
        import run_quality_bot
        bot = run_quality_bot.main
        bot.build_video_for_item = bot.create_voiceover = bot.upload_to_youtube = blocked
        history = bot.load_json(bot.HISTORY_FILE, {'processed_news': []})
        pool = bot.fetch_news_pool(hours_back=72)
        selector = getattr(bot, 'choose_six_with_content', None) or getattr(bot, 'choose_top_three', None) or bot.choose_six
        selected = selector(pool, history)
        for item in selected:
            try:
                if not item.get('article_text'):
                    item['article_text'] = bot.fetch_article_content(item)
                report.setdefault('source_candidates', []).append(copy.deepcopy(item))
                save()
                item['script'] = bot.generate_news_script(item)
                report['samples'].append(item)
                break
            except (ValueError, RuntimeError) as exc:
                report['errors'].append({'source': item.get('title'), 'error': str(exc)})
                save()
        if not report['samples']:
            raise RuntimeError('No source-grounded genuine Groq news package')
    report['complete'] = True
    save()
    print(json.dumps({'text_only': True, 'samples': len(report['samples']), 'report': str(out / 'report.json')}, ensure_ascii=False))
except Exception as exc:
    report['errors'].append({'type': type(exc).__name__, 'error': str(exc)})
    save()
    traceback.print_exc()
    raise

"""Six-slot runner with immediate receipts and no dry-run history pollution."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from youtube_receipt import confirm


def run(bot, *, quiz=False):
    dry = os.getenv('ENABLE_YOUTUBE_UPLOAD', '0') != '1' if quiz else os.getenv('DRY_RUN', '0') == '1'
    history = bot.load_json(bot.HISTORY_FILE, {'processed_news': []})
    report = {'run_id': os.getenv('GITHUB_RUN_ID', 'local'), 'generated_at': bot.now_tr().isoformat(), 'dry_run': dry, 'videos': [], 'errors': []}
    bot.save_json(Path('run_report.json'), report)
    pool = bot.fetch_news_pool(hours_back=72 if 'global' in bot.__doc__.lower() else 20)
    selector = getattr(bot, 'choose_six_with_content', None) or getattr(bot, 'choose_top_three', None) or bot.choose_six
    selected = selector(pool, history)
    if len(selected) != 6:
        raise RuntimeError(f'Six new items required; found {len(selected)}')
    prepared = []
    used = {str(row.get('fingerprint')) for row in history.get('processed_news', [])}
    primary = {str(row.get('fingerprint')) for row in selected}
    candidates = selected + [row for row in pool if str(row.get('fingerprint')) not in used | primary]
    for item in candidates:
        if len(prepared) == 6:
            break
        try:
            if hasattr(bot, 'fetch_article_content') and not item.get('article_text'):
                item['article_text'] = bot.fetch_article_content(item)
            item['script'] = bot.generate_news_script(item)
            prepared.append(item)
        except (ValueError, RuntimeError) as exc:
            if quiz:
                raise
            report['errors'].append({'source': item.get('title'), 'stage': 'generation', 'error': str(exc)})
            bot.save_json(Path('run_report.json'), report)
            bot.logger.warning('Source failed Groq validation; selecting another real source: %s', exc)
        if len(report['errors']) >= 12:
            break
    if len(prepared) != 6:
        raise RuntimeError(f'Six validated Groq scripts required: {len(prepared)}/6')
    bot.save_json(bot.SELECTED_FILE, {'generated_at': report['generated_at'], 'selected_news': prepared})
    current = bot.now_tr()
    reserved = set()
    for row in history.get('processed_news', []):
        try:
            reserved.add(datetime.fromisoformat(row.get('publish_at_local', '')))
        except ValueError:
            pass
    times = []
    for offset in range(31):
        for hour in (0, 4, 8, 12, 16, 20):
            target = (current + timedelta(days=offset)).replace(hour=hour, minute=0, second=0, microsecond=0)
            if target > current + timedelta(minutes=30) and target not in reserved:
                times.append(target)
    times = sorted(times)[:6]
    if len(times) != 6:
        raise RuntimeError('Six unreserved scheduled slots required')
    for index, (item, at) in enumerate(zip(prepared, times), 1):
        item['scheduled_slot'] = at.strftime('%H:%M')
        try:
            error = None
            for attempt in range(3):
                try:
                    item.update(bot.build_video_for_item(item, index))
                    break
                except Exception as exc:
                    error = exc
                    if attempt == 2:
                        raise
                    bot.logger.warning('Render %s/3 retry, same validated script: %s', attempt + 1, error)
                    time.sleep(5)
            # No whole-process retries: an accepted insert must never be repeated.
            result = bot.upload_to_youtube(Path(item['video_path']), item, at)
            item.update(result)
            row = {**result, 'index': index, 'title': item['title'], 'narration': item['spoken_text'],
                   'description': item.get('youtube_description', item.get('summary')), 'visual_query': item.get('visual_query', item.get('quiz', {}).get('visual_query')),
                   'tags': item.get('youtube_tags', []), 'video_path': item['video_path'], 'source_headline': item.get('source_headline'),
                   'run_id': report['run_id'], 'upload_status': 'dry_run' if dry else 'api_insert_confirmed'}
            report['videos'].append(row)
            # Persist the ID before attempting processing checks or the next slot.
            if not dry:
                history = bot.load_json(bot.HISTORY_FILE, history)
                known = {r.get('video_id') for r in history.get('processed_news', [])}
                if result['video_id'] not in known:
                    history = bot.update_history(history, [item])
                for saved in history.get('processed_news', []):
                    if saved.get('fingerprint') == item.get('fingerprint'):
                        saved.update(result, upload_status='api_insert_confirmed')
                bot.save_json(bot.HISTORY_FILE, history)
            bot.save_json(Path('run_report.json'), report)
            bot.save_json(bot.PLAN_FILE, {'generated_at': report['generated_at'], 'videos': report['videos']})
            if not dry:
                try:
                    receipt = confirm(bot.get_youtube_service(), result['video_id'])
                    row.update(receipt)
                    for saved in history.get('processed_news', []):
                        if saved.get('video_id') == result['video_id']:
                            saved.update(receipt)
                    bot.save_json(bot.HISTORY_FILE, history)
                except Exception as exc:
                    row['verification_error'] = str(exc)
                    report['errors'].append({'index': index, 'stage': 'readback', 'video_id': result['video_id'], 'error': str(exc)})
            bot.logger.info('Slot %s/6: %s %s', index, row['upload_status'], result['youtube_url'])
        except Exception as exc:
            report['errors'].append({'index': index, 'stage': 'render_or_upload', 'error': str(exc)})
            bot.logger.exception('Slot %s failed; continuing other slots', index)
        bot.save_json(Path('run_report.json'), report)
        bot.save_json(bot.PLAN_FILE, {'generated_at': report['generated_at'], 'videos': report['videos']})
    complete = len(report['videos']) == 6 and all(row['upload_status'] == ('dry_run' if dry else 'youtube_processed') for row in report['videos'])
    report['complete'] = complete
    bot.save_json(Path('run_report.json'), report)
    if not complete:
        raise RuntimeError('Six confirmed videos not completed; inspect run_report.json. Accepted IDs are saved; never reupload them.')
    bot.logger.info('Completed: 6/6 %s', 'rendered dry run' if dry else 'YouTube processed')

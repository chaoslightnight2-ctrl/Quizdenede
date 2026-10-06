"""Incremental daily publishing with saved receipts and no substitute content."""
from __future__ import annotations
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from youtube_receipt import confirm
from publish_schedule import next_slot

def run(bot, *, quiz=False):
    target_count = int(os.getenv('DAILY_VIDEO_COUNT', '3'))
    if target_count not in (3, 6):
        raise ValueError('DAILY_VIDEO_COUNT must be 3 or 6')
    dry = os.getenv('ENABLE_YOUTUBE_UPLOAD', '0') != '1' if quiz else os.getenv('DRY_RUN', '0') == '1'
    history = bot.load_json(bot.HISTORY_FILE, {'processed_news': []})
    report = {'run_id': os.getenv('GITHUB_RUN_ID', 'local'), 'generated_at': bot.now_tr().isoformat(), 'target_count': target_count, 'dry_run': dry, 'complete': False, 'videos': [], 'errors': []}
    bot.save_json(Path('run_report.json'), report)
    if quiz and hasattr(bot, 'iter_news_items'):
        candidates = bot.iter_news_items(history, target_count)
    else:
        pool = bot.fetch_news_pool(hours_back=72 if 'global' in bot.__doc__.lower() else 20)
        selector = getattr(bot, 'choose_six_with_content', None) or getattr(bot, 'choose_top_three', None) or bot.choose_six
        selected = selector(pool, history)
        used = {str(row.get('fingerprint')) for row in history.get('processed_news', [])}
        primary = {str(row.get('fingerprint')) for row in selected}
        remaining = [row for row in pool if str(row.get('fingerprint')) not in used | primary]
        if not quiz and remaining:
            remaining = bot.enrich_and_rank(remaining)
            remaining.sort(key=lambda row: bool(row.get('direct_source')), reverse=True)
        candidates = selected + remaining
    prepared = []

    def publish(item, index):
        nonlocal history
        at = next_slot(bot.now_tr(), history.get('processed_news', []), target_count)
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
            # Groq/TTS can take time; recalculate before inserting the actual video.
            history = bot.load_json(bot.HISTORY_FILE, history)
            at = next_slot(bot.now_tr(), history.get('processed_news', []), target_count, preferred=at)
            item['scheduled_slot'] = at.strftime('%H:%M')
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
                from upload_checkpoint import checkpoint
                checkpoint([Path('run_report.json'), bot.HISTORY_FILE], bot.logger)
                try:
                    receipt = confirm(bot.get_youtube_service(), result['video_id'])
                    row.update(receipt)
                    for saved in history.get('processed_news', []):
                        if saved.get('video_id') == result['video_id']:
                            saved.update(receipt)
                    bot.save_json(bot.HISTORY_FILE, history)
                except Exception as exc:
                    if isinstance(exc, ValueError):
                        row['upload_status'] = 'youtube_rejected'
                    row['verification_error'] = str(exc)
                    report['errors'].append({'index': index, 'stage': 'readback', 'video_id': result['video_id'], 'error': str(exc)})
            bot.logger.info('Slot %s: %s %s', index, row['upload_status'], result['youtube_url'])
        except Exception as exc:
            report['errors'].append({'index': index, 'stage': 'render_or_upload', 'error': str(exc)})
            bot.logger.exception('Slot %s failed; continuing other slots', index)
        bot.save_json(Path('run_report.json'), report)
        bot.save_json(bot.PLAN_FILE, {'generated_at': report['generated_at'], 'videos': report['videos']})

    for item in candidates:
        accepted = sum(row['upload_status'] in ({'dry_run'} if dry else {'api_insert_confirmed', 'youtube_processed'}) for row in report['videos'])
        if accepted >= target_count:
            break
        try:
            if hasattr(bot, 'fetch_article_content') and not item.get('article_text'):
                item['article_text'] = bot.fetch_article_content(item)
            item['script'] = bot.generate_news_script(item)
        except (ValueError, RuntimeError) as exc:
            report['errors'].append({'source': item.get('title'), 'stage': 'generation', 'error': str(exc)})
            bot.save_json(Path('run_report.json'), report)
            if quiz:
                raise
            bot.logger.warning('Source failed existing validation; next real source: %s', exc)
            if len(report['errors']) >= 60:
                break
            continue
        prepared.append(item)
        bot.save_json(bot.SELECTED_FILE, {'generated_at': report['generated_at'], 'selected_news': prepared})
        publish(item, len(prepared))
    allowed = {'dry_run'} if dry else {'api_insert_confirmed', 'youtube_processed'}
    accepted = sum(row['upload_status'] in allowed for row in report['videos'])
    report['complete'] = accepted == target_count
    bot.save_json(Path('run_report.json'), report)
    if not report['complete']:
        raise RuntimeError(f'{accepted}/{target_count} confirmed videos completed; saved insert IDs must not be reuploaded')
    bot.logger.info('Completed: %s/%s inserts accepted; individual processing/publication remains separate', accepted, target_count)

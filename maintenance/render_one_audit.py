"""Render one real Groq video through production code, never insert on YouTube."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import traceback

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
os.environ['DRY_RUN'] = '1'
os.environ['ENABLE_YOUTUBE_UPLOAD'] = '0'
os.environ['PUBLISH_UPLOAD_CHECKPOINTS'] = '0'
OUT = ROOT / 'quality-audit'
OUT.mkdir(exist_ok=True)
report = {'run_id': os.getenv('GITHUB_RUN_ID'), 'commit': os.getenv('GITHUB_SHA'),
          'no_upload': True, 'complete': False, 'errors': []}

def save():
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

def inspect(video, audio, sidecar):
    video, audio, sidecar = map(Path, (video, audio, sidecar))
    for source, target in ((video, 'final.mp4'), (audio, 'voice.mp3'), (sidecar, 'voice.words.json')):
        shutil.copyfile(source, OUT / target)
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)]))
    duration = float(info['format']['duration'])
    report['media'] = {'duration': duration, 'streams': [{key: s.get(key) for key in ('codec_type', 'codec_name', 'width', 'height', 'duration', 'sample_rate', 'channels')} for s in info['streams']]}
    audio_check = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(video), '-af', 'volumedetect,silencedetect=noise=-40dB:d=0.4', '-f', 'null', '-'], capture_output=True, text=True, check=True)
    report['audio_measurements'] = '\n'.join(line for line in audio_check.stderr.splitlines() if any(word in line for word in ('mean_volume', 'max_volume', 'silence_start', 'silence_end')))
    from PIL import Image, ImageDraw
    cells = []
    for index, fraction in enumerate((.04, .15, .3, .45, .6, .75, .88, .96)):
        frame = OUT / f'frame-{index}.jpg'
        at = duration * fraction
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(at), '-i', str(video), '-frames:v', '1', '-vf', 'scale=270:-2', '-y', str(frame)], check=True)
        with Image.open(frame) as img:
            cell = Image.new('RGB', (270, img.height + 25), 'white')
            cell.paste(img, (0, 25))
            ImageDraw.Draw(cell).text((6, 5), f'{at:.2f}s', fill='black')
            cells.append(cell)
    sheet = Image.new('RGB', (270 * 4, max(i.height for i in cells) * 2), 'white')
    for i, cell in enumerate(cells):
        sheet.paste(cell, ((i % 4) * 270, (i // 4) * cell.height))
    sheet.save(OUT / 'contact-sheet.jpg', quality=92)
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-y', str(OUT / 'actual-video-audio.wav')], check=True)
    report['complete'] = True
    save()

def news(family):
    import run_quality_bot
    bot = run_quality_bot.main
    bot.upload_to_youtube = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('Audit must never upload'))
    history = bot.load_json(bot.HISTORY_FILE, {'processed_news': []})
    pool = bot.fetch_news_pool(hours_back=72)
    selector = getattr(bot, 'choose_six_with_content', None) or getattr(bot, 'choose_top_three', None) or bot.choose_six
    selected = selector(pool, history)
    item = None
    for candidate in selected:
        try:
            if not candidate.get('article_text'):
                candidate['article_text'] = bot.fetch_article_content(candidate)
            candidate['script'] = bot.generate_news_script(candidate)
            item = candidate
            break
        except (ValueError, RuntimeError) as error:
            report['errors'].append({'stage': 'generation', 'source': candidate.get('title'), 'error': str(error)})
            save()
    if item is None:
        raise RuntimeError('No validated real Groq news script')
    report['content'] = item
    save()
    result = bot.build_video_for_item(item, 1)
    report['content'].update(result)
    from quality_gate import caption_chunks
    words = json.loads(Path(result['audio_path']).with_suffix('.words.json').read_text(encoding='utf-8'))
    report['captions'] = caption_chunks(words['words'])
    inspect(result['video_path'], result['audio_path'], Path(result['audio_path']).with_suffix('.words.json'))

def quiz():
    import run_quiz_with_sync
    import run_quiz_main as module
    bot = module.bot
    bot.upload_to_youtube = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('Audit must never upload'))
    history = bot.load_json(bot.HISTORY_FILE, {'processed_news': [], 'processed_questions': []})
    candidates = []
    for _ in range(5):
        candidates = module._generate_candidate_round(history)
        if candidates:
            break
    if not candidates:
        raise RuntimeError('No independently verified real Groq quiz')
    question = candidates[0]
    item = {'quiz': question, 'title': module.viral_title_for_quiz(question['question'], question['topic']),
            'summary': question['explanation'], 'query': question['topic'], 'fingerprint': question['id'], 'scheduled_slot': 'audit'}
    item['script'] = bot.generate_news_script(item)
    report['content'] = item
    save()
    result = bot.build_video_for_item(item, 1)
    report['content'].update(result)
    from quality_gate import caption_chunks
    words = json.loads(Path(result['audio_path']).with_suffix('.words.json').read_text(encoding='utf-8'))
    report['captions'] = caption_chunks(words['words'])
    inspect(result['video_path'], result['audio_path'], Path(result['audio_path']).with_suffix('.words.json'))

def denede():
    from src import pipeline
    original = pipeline._pick_script
    def record(*args, **kwargs):
        result = original(*args, **kwargs)
        report['content'] = result[0]
        save()
        return result
    pipeline._pick_script = record
    result = pipeline.run_once(upload_to_youtube=False)
    path = Path(result['path'])
    shutil.copyfile(path.parent / 'captions.ass', OUT / 'captions.ass')
    inspect(path, path.parent / 'voice.mp3', path.parent / 'voice.words.json')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('family', choices=('haber', 'global', 'quiz', 'denede'))
    family = parser.parse_args().family
    report['family'] = family
    save()
    try:
        if family == 'denede':
            denede()
        elif family == 'quiz':
            quiz()
        else:
            news(family)
    except Exception as exc:
        record = {'stage': 'render_audit', 'type': type(exc).__name__, 'error': str(exc)}
        response = getattr(exc, 'response', None)
        if response is not None:
            try:
                record['provider_error'] = response.json().get('error', {})
            except ValueError:
                pass
        report['errors'].append(record)
        save()
        traceback.print_exc()
        raise

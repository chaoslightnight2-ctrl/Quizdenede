"""Small bounded preferences learned only from real, mature video measurements."""
import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
try:
    from .audience_strategy import category
except ImportError:
    from audience_strategy import category

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'src':
    ROOT = ROOT.parent
REPORT = ROOT / 'performance/analytics.json'

def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None

def learn(rows, now=None):
    now = now or datetime.now(timezone.utc)
    eligible = []
    for row in rows:
        try:
            at = datetime.fromisoformat(row['published_at'].replace('Z', '+00:00'))
            if at.tzinfo is None or at > now - timedelta(hours=72):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        percent = number(row.get('averageViewPercentage'))
        engaged = number(row.get('engagedViews'))
        if percent is None or percent < 0 or engaged is None or engaged < 100:
            continue
        eligible.append({**row, 'averageViewPercentage': percent})
    if len(eligible) < 6:
        return {'status': 'insufficient_data', 'categories': {}, 'hook_styles': {}}
    baseline = statistics.median(r['averageViewPercentage'] for r in eligible)
    result = {'status': 'measured', 'sample_count': len(eligible), 'categories': {}, 'hook_styles': {}}
    for field, destination in [('audience_bucket', 'categories'), ('hook_style', 'hook_styles')]:
        for key in sorted({r.get(field, '') for r in eligible} - {'', 'other'}):
            group = [r for r in eligible if r.get(field) == key]
            if len(group) < 3:
                continue
            percent = statistics.median(r['averageViewPercentage'] for r in group)
            choice = [number(r.get('stayed_to_watch_pct')) for r in group]
            choice = [v for v in choice if v is not None and 0 <= v <= 100]
            all_choice = [number(r.get('stayed_to_watch_pct')) for r in eligible]
            all_choice = [v for v in all_choice if v is not None and 0 <= v <= 100]
            choice_delta = statistics.median(choice) - statistics.median(all_choice) if len(choice) >= 3 and len(all_choice) >= 6 else 0
            bonus = max(-8, min(8, (percent - baseline) * .15 + choice_delta * .1))
            result[destination][key] = {'videos': len(group), 'bonus': round(bonus, 2)}
    drops = [(number(r.get('largest_drop_at_video_fraction')), number(r.get('largest_drop_ratio'))) for r in eligible]
    early = sum(at is not None and drop is not None and at <= .15 and drop >= .08 for at, drop in drops)
    late = sum(at is not None and drop is not None and at >= .8 and drop >= .08 for at, drop in drops)
    result['pacing'] = {'early_drop_videos': early, 'late_drop_videos': late}
    return result

def read_feedback():
    try:
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        at = datetime.fromisoformat(report['generated_at'].replace('Z', '+00:00'))
        if report.get('status') != 'ok' or at < datetime.now(timezone.utc) - timedelta(days=7):
            return {}
        return report.get('learning', {})
    except (OSError, ValueError, KeyError, TypeError):
        return {}

def category_bonus(text):
    row = read_feedback().get('categories', {}).get(category(text), {})
    value = number(row.get('bonus'))
    return max(-8, min(8, value)) if value is not None else 0

def prompt_feedback():
    feedback = read_feedback()
    measured = {name: feedback.get(name, {}) for name in ('categories', 'hook_styles')}
    pacing = feedback.get('pacing', {})
    instruction = ''
    if pacing.get('early_drop_videos', 0) >= 3:
        instruction += ' Gerçek tutma eğrilerinde başlangıçta düşüş tekrarlandı İlk cümleyi daha kısa ve doğrudan ana meraka bağla'
    if pacing.get('late_drop_videos', 0) >= 3:
        instruction += ' Gerçek tutma eğrilerinde sonda düşüş tekrarlandı Sonuçtan sonra açıklamayı uzatma ve kapanışı kısa tut'
    if not any(measured.values()) and not instruction:
        return ''
    return ('\nGerçek eski video ölçümlerinden sınırlı tercihler Pozitif bonuslu konu veya giriş biçimine öncelik ver '
            'ama aynı metni soruyu veya olguyu tekrar etme Bunlar içerik veya kaynak değildir:\n'
            + json.dumps(measured, ensure_ascii=False) + instruction)

def choose_hook_style(history):
    styles = ('direct_change', 'concrete_question')
    rows = history.get('processed_news', history.get('published', []))
    measured = read_feedback().get('hook_styles', {})
    # Keep one fifth of introductions exploring; no winner from tiny samples.
    if all(style in measured for style in styles) and len(rows) % 5:
        return max(styles, key=lambda key: number(measured.get(key, {}).get('bonus')) or 0)
    counts = {style: sum(r.get('hook_style') == style for r in rows[-20:]) for style in styles}
    return min(styles, key=lambda key: (counts[key], styles.index(key)))

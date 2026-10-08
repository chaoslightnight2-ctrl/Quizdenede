"""Show the complete actual question from frame zero, using speech boundaries."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def question_image(question, font_path, width=940):
    if not Path(font_path).is_file():
        font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    font = ImageFont.truetype(font_path, 60)
    canvas = Image.new('RGBA', (width, 360), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    lines, line = [], ''
    for word in question.split():
        candidate = (line + ' ' + word).strip()
        if line and draw.textbbox((0, 0), candidate, font=font)[2] > width - 60:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    height = len(lines) * 78 + 42
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 160))
    draw = ImageDraw.Draw(canvas)
    for index, text in enumerate(lines):
        draw.text((width / 2, 20 + index * 78), text, font=font, fill='white', anchor='mt', stroke_width=2, stroke_fill='black')
    return canvas

def question_end(question, words):
    count = len(question.split())
    if not count or len(words) < count:
        raise ValueError('Question speech boundaries are missing')
    return float(words[count - 1][0] + words[count - 1][1])

def answer_start(words):
    for index in range(len(words) - 1):
        if [words[index][2].casefold(), words[index + 1][2].casefold()] == ['doğru', 'cevap']:
            return float(words[index][0])
    raise ValueError('Answer speech boundary missing')

def install(bot):
    original_build = bot.build_video_for_item
    original_assemble = bot.assemble_video
    original_captions = bot.generate_captions
    original_chunks = bot.chunk_timestamps
    context = {}

    def build(item, index):
        context['question'] = item['question_text']
        try:
            return original_build(item, index)
        finally:
            context.clear()

    def assemble(background, audio, video, words):
        context['question_end'] = question_end(context['question'], words)
        context['answer_start'] = answer_start(words)
        bot.chunk_timestamps = lambda rows: original_chunks(rows[len(context['question'].split()):])
        try:
            return original_assemble(background, audio, video, words)
        finally:
            bot.chunk_timestamps = original_chunks

    def captions(chunks):
        import numpy as np
        from moviepy.editor import ImageClip
        end = context['answer_start']
        # Later caption groups retain the existing measured voice timing.
        clips = original_captions(chunks)
        image = question_image(context['question'], bot.ensure_font(), bot.VIDEO_SIZE[0] - 140)
        clips.insert(0, ImageClip(np.array(image)).set_start(0).set_duration(end).set_position(('center', int(bot.VIDEO_SIZE[1] * .22))))
        for index, remaining in enumerate((3, 2, 1)):
            image = question_image(str(remaining), bot.ensure_font(), 180)
            clips.append(ImageClip(np.array(image)).set_start(max(0, end - 3) + index)
                         .set_duration(1).set_position(('center', int(bot.VIDEO_SIZE[1] * .46))))
        return clips

    bot.build_video_for_item = build
    bot.assemble_video = assemble
    bot.generate_captions = captions

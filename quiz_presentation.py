"""Show the complete actual question from frame zero, using speech boundaries."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def quiz_background_frame(width, height):
    """The primary quiz card design; no stock clip or model request is used."""
    import numpy as np
    y, x = np.mgrid[0:height, 0:width]
    glow = np.maximum(0, 1 - ((x / width - .5) ** 2 + (y / height - .3) ** 2) * 2)
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:, :, 0] = 10 + 15 * glow
    frame[:, :, 1] = 18 + 24 * glow
    frame[:, :, 2] = 35 + 44 * glow
    return frame


def write_quiz_background(path, size):
    from moviepy.editor import ImageClip
    clip = ImageClip(quiz_background_frame(*size)).set_duration(2)
    try:
        clip.write_videofile(str(path), codec='libx264', fps=24, audio=False,
                             preset='fast', threads=2, verbose=False, logger=None)
    finally:
        clip.close()

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
    # Every quiz uses its own question/countdown/answer presentation. Stock
    # availability must never decide whether a verified question can publish.
    bot.download_background_video = lambda item, path: write_quiz_background(path, bot.VIDEO_SIZE)

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

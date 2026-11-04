"""Fixed-layout explanation slides for the classroom player."""
import hashlib
import html
import json
import math
import re


class LayoutError(ValueError):
    pass


BACKGROUND = {'type': 'solid', 'color': '#FFF6E5'}
THEME = {
    'shadow': {'h': 0, 'v': 0, 'blur': 10, 'color': '#000000'},
    'outline': {'color': '#d14424', 'style': 'solid', 'width': 2},
    'fontName': 'Microsoft YaHei', 'fontColor': '#333333',
    'themeColors': ['#5b9bd5', '#ed7d31', '#a5a5a5', '#ffc000', '#4472c4'],
    'backgroundColor': '#ffffff',
}
SIZES = (140, 120, 100, 88, 72, 60, 52, 44, 40, 36, 32, 28, 26, 24, 22, 20, 18)
INK = '#6B4423'
ORANGE = '#E76F51'


def text_box(element):
    content = element.get('content', '')
    sizes = [float(x) for x in re.findall(r'font-size\s*:\s*([\d.]+)px', content, re.I)]
    size = max(sizes, default=16)
    paragraphs = re.split(r'</p\s*>|<br\s*/?>', content, flags=re.I)
    lines = 0
    width = max(float(element.get('width', 0)) - 20, 1)
    for part in paragraphs:
        text = html.unescape(re.sub(r'<[^>]*>', '', part))
        if text.strip():
            units = sum(1 if ord(ch) > 127 else 0.55 for ch in text)
            lines += max(1, math.ceil(units * size / width))
    height = 20 + max(lines, 1) * size * 1.5 + max(0, lines - 1) * 5
    left, top = float(element.get('left', 0)), float(element.get('top', 0))
    return left, top, left + float(element.get('width', 0)), top + height


def _string(data, key, limit=60):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise LayoutError('bad_data', key)
    return value


def _list(data, key, minimum, maximum):
    value = data.get(key)
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise LayoutError('bad_data', key)
    for item in value:
        _string({'item': item}, 'item')
    return value


class _Slide:
    def __init__(self, image_urls, aspects):
        self.elements = []
        self.names = {}
        self.image_urls = image_urls
        self.aspects = aspects

    def text(self, name, value, box, maximum, align='center', color=INK):
        left, top, width, height = box
        element = {'id': 'text_' + name, 'type': 'text', 'left': left, 'top': top,
                   'width': width, 'height': height, 'rotate': 0, 'content': '',
                   'defaultColor': color, 'defaultFontName': 'Microsoft YaHei'}
        for size in SIZES:
            if size > maximum:
                continue
            element['content'] = '<p style="font-size:%dpx; text-align:%s; color:%s;"><strong>%s</strong></p>' % (
                size, align, color, html.escape(value))
            if text_box(element)[3] <= top + height:
                self.elements.append(element)
                self.names[name] = element['id']
                return
        raise LayoutError('text_too_long', name)

    def shape(self, name, box, fill='#FFE3B3', path='M 0 0 L 1 0 L 1 1 L 0 1 Z'):
        left, top, width, height = box
        self.elements.append({'id': 'shape_' + name, 'type': 'shape', 'left': left,
                              'top': top, 'width': width, 'height': height, 'rotate': 0,
                              'fill': fill, 'path': path, 'viewBox': [1, 1], 'fixedRatio': False})

    def image(self, name, key, box):
        if key not in self.image_urls:
            raise LayoutError('image_missing', key)
        url = self.image_urls[key]
        aspect = self.aspects.get(key, 16 / 9)
        if not isinstance(url, str) or not url.strip() or isinstance(aspect, bool) or not isinstance(aspect, (int, float)) or not math.isfinite(aspect) or aspect <= 0:
            raise LayoutError('bad_data', name)
        left, top, width, height = box
        w = min(width, height * aspect)
        h = w / aspect
        element = {'id': 'image_' + name, 'type': 'image', 'src': url,
                   'left': left + (width - w) / 2, 'top': top + (height - h) / 2,
                   'width': w, 'height': h, 'rotate': 0, 'fixedRatio': True}
        self.elements.append(element)
        self.names[name] = element['id']

    def title(self, data):
        self.text('title', _string(data, 'title'), (60, 22, 880, 74), 40, color=ORANGE)


def _title_picture(s, data):
    s.title(data)
    s.image('picture', _string(data, 'picture'), (120, 108, 760, 332))
    if 'caption' in data:
        s.text('caption', _string(data, 'caption'), (60, 452, 880, 70), 28)


def _picture_points(s, data):
    s.title(data)
    s.image('picture', _string(data, 'picture'), (50, 112, 420, 300))
    points = _list(data, 'points', 1, 4)
    height = min(110, (408 - 14 * (len(points) - 1)) / len(points))
    for i, point in enumerate(points):
        top = 112 + i * (height + 14)
        name = 'point-%d' % (i + 1)
        s.shape('card-%d' % (i + 1), (500, top, 450, height))
        s.text(name, point, (512, top + 12, 426, height - 24), 28, 'left')


def _two_columns(s, data):
    s.title(data)
    for name, left in (('left', 50), ('right', 520)):
        column = data.get(name)
        if not isinstance(column, dict):
            raise LayoutError('bad_data', name)
        heading = _string(column, 'heading')
        body = _string(column, 'body')
        s.shape(name + '-card', (left, 112, 430, 418))
        s.text(name + '-heading', heading, (left + 12, 124, 406, 54), 32)
        top = 190
        key = name + '_picture'
        if key in data:
            s.image(name + '-picture', _string(data, key), (left + 12, 190, 406, 200))
            top = 402
        s.text(name + '-body', body, (left + 12, top, 406, 518 - top), 26, 'left')


def _big_word(s, data):
    if 'title' in data:
        s.title(data)
    word = _string(data, 'word', 6)
    if 'pinyin' in data:
        s.text('pinyin', _string(data, 'pinyin'), (50, 120, 430, 74), 36)
        word_top = 204
    else:
        word_top = 120
    s.text('word', word, (50, word_top, 430, 380 - word_top), 140, color=ORANGE)
    if 'picture' in data:
        s.image('picture', _string(data, 'picture'), (520, 110, 430, 290))
    s.text('hint', _string(data, 'hint'), (60, 420, 880, 100), 30)


def _steps(s, data):
    s.title(data)
    steps = _list(data, 'steps', 2, 5)
    width = (900 - 14 * (len(steps) - 1)) / len(steps)
    for i, step in enumerate(steps):
        left = 50 + i * (width + 14)
        s.shape('card-%d' % (i + 1), (left, 130, width, 340))
        s.shape('badge-%d' % (i + 1), (left + (width - 80) / 2, 150, 80, 80), '#F6A935',
                'M 0.5 0 A 0.5 0.5 0 1 1 0.5 1 A 0.5 0.5 0 1 1 0.5 0 Z')
        s.text('number-%d' % (i + 1), str(i + 1), (left + (width - 80) / 2, 150, 80, 80), 40)
        s.text('step-%d' % (i + 1), step, (left + 12, 245, width - 24, 213), 26)


def _summary(s, data):
    s.title(data)
    items = _list(data, 'items', 2, 5)
    height = min(90, (418 - 14 * (len(items) - 1)) / len(items))
    for i, item in enumerate(items):
        top = 112 + i * (height + 14)
        s.shape('card-%d' % (i + 1), (50, top, 900, height))
        s.text('tick-%d' % (i + 1), '✓', (62, top + 6, 56, height - 12), 28, color=ORANGE)
        s.text('item-%d' % (i + 1), item, (130, top + 6, 808, height - 12), 28, 'left')


TEMPLATES = {'title-picture': _title_picture, 'picture-points': _picture_points,
             'two-columns': _two_columns, 'big-word': _big_word, 'steps': _steps,
             'summary': _summary}


def template_names():
    return list(TEMPLATES)


def render(template, data, *, image_urls, aspects=None):
    if not isinstance(template, str) or template not in TEMPLATES:
        raise LayoutError('unknown_template', str(template))
    if not isinstance(data, dict) or not isinstance(image_urls, dict) or (aspects is not None and not isinstance(aspects, dict)):
        raise LayoutError('bad_data', 'data, image_urls or aspects')
    slide = _Slide(image_urls, aspects if aspects is not None else {})
    TEMPLATES[template](slide, data)
    return {'elements': slide.elements, 'names': slide.names, 'background': dict(BACKGROUND)}


def canvas(elements, background=None):
    encoded = json.dumps(elements, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return {'id': hashlib.sha256(encoded.encode('utf-8')).hexdigest(),
            'theme': json.loads(json.dumps(THEME)), 'elements': elements,
            'background': dict(BACKGROUND) if background is None else background,
            'viewportSize': 1000, 'viewportRatio': 0.5625}

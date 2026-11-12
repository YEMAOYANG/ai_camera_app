"""Draw exact relative lengths, pressure positions and visible shape changes."""

from hashlib import sha256
from pathlib import Path
import json

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
PAPER, FRAME, GREEN = '#fff4dd', '#dfe9ce', '#57755a'
STEEL, EDGE, SIGNAL = '#8b989d', '#384d53', '#ac532e'
FAIR = ((214, 14, 157), (214, 14, 157))
TEACHING_SETUP = (*FAIR, FAIR[0])
UNEQUAL_LENGTH = ((214, 14, 157), (154, 14, 157))
UNEQUAL_PRESS = ((214, 14, 157), (214, 14, 119))
BEFORE_TIP, AFTER_TIP = 44, 20


def board(size):
    image = Image.new('RGB', size, PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((9, 9, size[0]-10, size[1]-10), 18, fill=FRAME, outline=GREEN, width=4)
    return image, draw


def arrow(draw, x, y):
    draw.line((x, y-46, x, y-16), fill=SIGNAL, width=7)
    draw.polygon(((x-12,y-19), (x+12,y-19), (x,y-7)), fill=SIGNAL)


def setup_pair(samples, wide=False):
    image, draw = board((64+313*len(samples), 300) if wide else (412, 350))
    for i, (length, thickness, pressure) in enumerate(samples):
        left = 56 + (313*i if wide else 0)
        y = 165 if wide else 116+149*i
        draw.rounded_rectangle((left-16,y-27,left+28,y+37),6,fill=GREEN,outline=EDGE,width=3)
        draw.rounded_rectangle((left,y,left+length,y+thickness),5,fill=STEEL,outline=EDGE,width=3)
        arrow(draw,left+pressure,y)
    return image


def flatten_pair(single=False):
    image, draw = board((310, 226) if single else (700, 306))
    for i, tip in enumerate((AFTER_TIP,) if single else (BEFORE_TIP,AFTER_TIP)):
        x = 35+330*i
        y = 110 if single else 153
        end=x+235
        draw.polygon(((x,y-BEFORE_TIP//2), (end-64,y-BEFORE_TIP//2), (end-38,y-tip//2),
                      (end,y-tip//2), (end,y+tip//2), (end-38,y+tip//2),
                      (end-64,y+BEFORE_TIP//2), (x,y+BEFORE_TIP//2)),
                     fill=STEEL,outline=EDGE,width=4)
        draw.line((end-42,y-tip//2,end-42,y+tip//2),fill=SIGNAL,width=5)
    if not single:
        draw.line((309,153,344,153),fill=SIGNAL,width=6)
        draw.polygon(((339,141),(339,165),(356,153)),fill=SIGNAL)
    return image


def bend_result(direction):
    image, draw = board((310, 226))
    line=[(x,125+direction*round(max(0,x-108)**2/480)) for x in range(37,273)]
    draw.line(line,fill=EDGE,width=21)
    draw.line(line,fill=STEEL,width=13)
    return image


def quiz_tip_view(view):
    image, draw = board((348, 231))
    if view=='top':
        draw.rounded_rectangle((53,79,291,152),16,fill=STEEL,outline=EDGE,width=4)
    elif view=='side':
        draw.polygon(((53,88),(217,88),(249,108),(291,108),(291,124),(249,124),
                      (217,144),(53,144)),fill=STEEL,outline=EDGE,width=4)
    else:
        draw.rounded_rectangle((53,88,291,144),7,fill=STEEL,outline=EDGE,width=4)
    draw.line((273,113,286,113),fill=SIGNAL,width=6)
    return image


def render():
    items = {
        'fair-bend-conditions': (setup_pair(TEACHING_SETUP,True), ['bend-the-same-way']),
        'fair-setup-quiz': (setup_pair(FAIR), ['picture-quiz']),
        'unequal-length-quiz': (setup_pair(UNEQUAL_LENGTH), ['picture-quiz']),
        'unequal-pressure-quiz': (setup_pair(UNEQUAL_PRESS), ['picture-quiz']),
        'flattened-end-comparison': (flatten_pair(), ['listen-and-flatten']),
        'result-flat-tip': (flatten_pair(True), ['sort-metal-evidence']),
        'result-bent-up': (bend_result(-1), ['sort-metal-evidence']),
        'result-bent-down': (bend_result(1), ['sort-metal-evidence']),
        'quiz-tip-top': (quiz_tip_view('top'), ['picture-quiz']),
        'quiz-tip-side': (quiz_tip_view('side'), ['picture-quiz']),
        'quiz-tip-straight': (quiz_tip_view('straight'), ['picture-quiz']),
    }
    path = ROOT/'asset-sources.json'
    manifest = json.loads(path.read_text()) if path.exists() else {
        'schemaVersion': 'mira.courseware.asset-sources.v1', 'assets': {},
    }
    source = Path(__file__).resolve()
    digest = lambda p: sha256(p.read_bytes()).hexdigest()
    for key, (image, uses) in items.items():
        dest = ROOT/'assets'/f'{key}.png'
        image.save(dest,optimize=True)
        manifest['assets'][key] = {
            'file': dest.relative_to(ROOT).as_posix(), 'sha256': digest(dest),
            'kind': 'deterministic-lesson-diagram', 'source': source.relative_to(ROOT).as_posix(),
            'sourceSha256': digest(source), 'usedBy': uses,
        }
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    render()

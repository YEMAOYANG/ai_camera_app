"""Render the shared waterline, sample sizes, and paper-tear outcome models."""

from hashlib import sha256
from pathlib import Path
import json

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
PAPER, BORDER, FRAME = '#fff5df', '#59765d', '#e0ebd7'
WATER, WATERLINE = '#b0d8e0', 247
BLUE, WET, DRY = '#326c89', '#68afbf', '#fff2d2'
START, BOTTOM, WIDTH = 68, 286, 52
FAIR = ((WIDTH, BOTTOM), (WIDTH, BOTTOM))
UNEQUAL_WIDTH = ((WIDTH, BOTTOM), (78, BOTTOM))
UNEQUAL_DIP = ((WIDTH, BOTTOM), (WIDTH, BOTTOM+19))
QUIZ_RISE = (31, 65, 113)


def board(size):
    image = Image.new('RGB', size, PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, size[0]-9, size[1]-9),16,fill=FRAME,outline=BORDER,width=4)
    return image, draw


def basin(samples, rises=None):
    image, draw = board((456, 333))
    draw.rectangle((40, WATERLINE, 416, 309),fill=WATER)
    draw.line((40, 192, 40, 309, 416, 309, 416, 192),fill=BLUE,width=5)
    draw.line((70,57,386,57),fill='#7f664e',width=7)
    for i, (width, bottom) in enumerate(samples):
        x = (228,) if len(samples)==1 else (144,312)
        left,right=x[i]-width//2,x[i]+width//2
        top=bottom-(BOTTOM-START)
        draw.rectangle((left,top,right,bottom),fill=DRY,outline='#9b835b',width=3)
        rise=rises[i] if rises else 0
        if rise:
            draw.rectangle((left+3,WATERLINE-rise,right-3,bottom-3),fill=WET)
            draw.line((left+3,WATERLINE-rise,right-3,WATERLINE-rise),fill=BLUE,width=4)
        draw.rounded_rectangle((x[i]-9,52,x[i]+9,top+7),4,fill='#a07549')
    for x in range(41,411,15):
        draw.line((x,WATERLINE,x+8,WATERLINE),fill=BLUE,width=3)
    return image


def tug_result(whole,colors=('#d9a76b','#a1c6d0')):
    image,draw=board((456,270))
    for y,intact,color in zip((77,185),whole,colors):
        if intact:
            draw.rectangle((66,y,390,y+27),fill=color,outline=BORDER,width=4)
        else:
            draw.polygon(((66,y),(212,y),(202,y+8),(211,y+16),(198,y+27),(66,y+27)),
                         fill=color,outline=BORDER,width=4)
            draw.polygon(((245,y),(390,y),(390,y+27),(236,y+27),(247,y+18),(239,y+10)),
                         fill=color,outline=BORDER,width=4)
    return image


def render():
    items={
        'water-comparison-model':(basin(FAIR,(110,34)),['same-start-water']),
        'water-setup-fair':(basin(FAIR),['picture-quiz']),
        'water-setup-width':(basin(UNEQUAL_WIDTH),['picture-quiz']),
        'water-setup-depth':(basin(UNEQUAL_DIP),['picture-quiz']),
        'tug-result-guide':(tug_result((True,False),('#d9a76b','#faf4dc')),['paper-tug']),
        'tug-both-torn':(tug_result((False,False)),['picture-quiz']),
        'tug-kraft-holds':(tug_result((True,False)),['picture-quiz']),
        'tug-other-holds':(tug_result((False,True)),['picture-quiz']),
    }
    for tag,rise in zip(('low','middle','high'),QUIZ_RISE):
        items[f'water-height-{tag}']=(basin((FAIR[0],),(rise,)),['picture-quiz'])
    path=ROOT/'asset-sources.json'
    records=json.loads(path.read_text()) if path.exists() else {
        'schemaVersion':'mira.courseware.asset-sources.v1','assets':{},
    }
    source=Path(__file__).resolve()
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    for key,(image,uses) in items.items():
        target=ROOT/'assets'/f'{key}.png'
        image.save(target,optimize=True)
        records['assets'][key]=dict(file=target.relative_to(ROOT).as_posix(),sha256=digest(target),
            kind='deterministic-lesson-diagram',source=source.relative_to(ROOT).as_posix(),sourceSha256=digest(source),usedBy=uses)
    path.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    render()

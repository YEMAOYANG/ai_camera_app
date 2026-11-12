"""Draw exact top-view placement and side-view lid clearance."""

from hashlib import sha256
from pathlib import Path
import json

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
PAPER, INK, GREEN, MINT = '#fff5de', '#29483b', '#55745a', '#dcead5'
ORANGE, BLUE, WALL = '#dca06b', '#85acba', '#9a7a59'
VIOLET, OCHRE, LILAC_WALL = '#9a87ba', '#dfb673', '#705d89'
CASE = (66, 64, 418, 249)
EXAMPLE_BAD = ((106, 44, 67, 220), (249, 109, 117, 86))
EXAMPLE_FITS = ((95, 77, 220, 67), (249, 154, 117, 86))
QUIZ_OVERLAP = ((100, 88, 213, 61), (232, 116, 108, 83))
QUIZ_FITS = ((93, 82, 213, 61), (261, 154, 108, 83))
QUIZ_OUTSIDE = ((117, 56, 61, 213), (251, 103, 108, 83))
LID_Y, FLOOR_Y = 100, 259
LID_LEFT, LID_RIGHT = 66, 420
LEFT_BLOCK, RIGHT_BLOCK = (123, 109), (267, 101)
LID_LIMIT = FLOOR_Y-LID_Y


def board(size):
    image = Image.new('RGB', size, PAPER)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8,8,size[0]-9,size[1]-9),16,fill=MINT,outline=GREEN,width=4)
    return image,draw


def packing_top(items, *, pieces=(ORANGE,BLUE), wall=WALL):
    image,draw=board((485,310))
    draw.rounded_rectangle(CASE,12,fill='#f8ddaf',outline=wall,width=8)
    for (x,y,w,h),fill in zip(items,pieces):
        draw.rounded_rectangle((x,y,x+w,y+h),6,fill=fill,outline=INK,width=4)
        draw.line((x+8,y+10,x+w-8,y+10),fill='#ffe8c2',width=3)
    return image


def lid_side(left_height,right_height, *, pieces=(ORANGE,BLUE), wall=WALL):
    image,draw=board((485,310))
    draw.rectangle((72,LID_Y,413,FLOOR_Y),fill='#f1dab6')
    draw.line((72,LID_Y,72,FLOOR_Y,413,FLOOR_Y,413,LID_Y),fill=wall,width=8)
    for (x,width),height,fill in zip((LEFT_BLOCK, RIGHT_BLOCK), (left_height, right_height), pieces):
        draw.rectangle((x,FLOOR_Y-height,x+width,FLOOR_Y-4),fill=fill,outline=INK,width=4)
    span=LID_RIGHT-LID_LEFT
    left_top=max(0,left_height-LID_LIMIT)
    right_top=max(0,right_height-LID_LIMIT)
    # The raised lid touches the inner corner of the tall piece.
    left=LID_Y-round(left_top*span/(LID_RIGHT-sum(LEFT_BLOCK)))
    right=LID_Y-round(right_top*span/(RIGHT_BLOCK[0]-LID_LEFT))
    draw.line((LID_LEFT,left,LID_RIGHT,right),fill=INK,width=9)
    return image


def comparison(left,right):
    out=Image.new('RGB',(984,310),PAPER)
    out.paste(left,(0,0))
    out.paste(right,(499,0))
    return out


def render():
    quiz_colors=dict(pieces=(VIOLET,OCHRE),wall=LILAC_WALL)
    items={
        'turn-to-fit-model':(comparison(packing_top(EXAMPLE_BAD),packing_top(EXAMPLE_FITS)),['turn-and-fit']),
        'test-the-lid-model':(comparison(lid_side(172,91),lid_side(103,91)),['turn-and-fit']),
        'box-layout-overlap':(packing_top(QUIZ_OVERLAP,**quiz_colors),['picture-quiz']),
        'box-layout-fit':(packing_top(QUIZ_FITS,**quiz_colors),['picture-quiz']),
        'box-layout-outside':(packing_top(QUIZ_OUTSIDE,**quiz_colors),['picture-quiz']),
        'lid-lifted-left':(lid_side(174,82,**quiz_colors),['picture-quiz']),
        'lid-lifted-right':(lid_side(115,175,**quiz_colors),['picture-quiz']),
        'lid-fits-both':(lid_side(115,108,**quiz_colors),['picture-quiz']),
    }
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

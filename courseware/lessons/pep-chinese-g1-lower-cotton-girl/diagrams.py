"""Draw seven exact handwriting paths and the spotted paper models."""
from pathlib import Path

from PIL import Image, ImageDraw


PAPER, LINE, PINE, ACTIVE = "#fff2da", "#d9ba87", "#26473d", "#b84d2c"

# GF 0023—2020 printed pages 3, 5, 32, 40, 46, 102 and 135.
STROKES = {
    "她": (
        (5, ((.29,.20),(.22,.55),(.34,.73))),
        (3, ((.39,.33),(.37,.53),(.31,.70),(.18,.82))),
        (1, ((.15,.45),(.43,.38))),
        (5, ((.45,.46),(.83,.36),(.81,.58),(.78,.63),(.74,.58))),
        (2, ((.64,.21),(.63,.67))),
        (5, ((.53,.32),(.52,.74),(.55,.81),(.70,.83),(.85,.81),(.88,.76),(.89,.67))),
    ),
    "空": (
        (4, ((.45,.15),(.53,.23))), (4, ((.23,.29),(.21,.40))),
        (5, ((.25,.30),(.78,.28),(.73,.40))),
        (3, ((.42,.41),(.34,.51),(.25,.56))), (4, ((.58,.42),(.68,.50),(.73,.55))),
        (1, ((.32,.62),(.68,.61))), (2, ((.50,.62),(.50,.81))),
        (1, ((.21,.83),(.80,.81))),
    ),
    "还": (
        (1, ((.39,.26),(.85,.24))), (3, ((.63,.27),(.54,.45),(.39,.54))),
        (2, ((.60,.34),(.60,.67))), (4, ((.70,.41),(.81,.52))),
        (4, ((.20,.24),(.28,.35))),
        (5, ((.16,.46),(.30,.43),(.25,.55),(.31,.62),(.24,.72))),
        (4, ((.14,.75),(.23,.72),(.35,.77),(.53,.82),(.70,.83),(.88,.79))),
    ),
    "干": (
        (1, ((.28,.32),(.72,.30))), (1, ((.16,.55),(.83,.53))),
        (2, ((.50,.31),(.50,.85))),
    ),
    "身": (
        (3, ((.49,.16),(.42,.30))), (2, ((.35,.33),(.35,.66))),
        (5, ((.35,.33),(.66,.31),(.65,.81),(.62,.86),(.55,.79))),
        (1, ((.35,.43),(.65,.41))), (1, ((.35,.54),(.65,.52))),
        (1, ((.26,.68),(.69,.64))),
        (3, ((.76,.52),(.64,.67),(.48,.77),(.25,.85))),
    ),
    "星": (
        (2, ((.32,.20),(.33,.46))), (5, ((.32,.20),(.69,.18),(.67,.46))),
        (1, ((.33,.32),(.67,.30))), (1, ((.33,.44),(.67,.42))),
        (3, ((.34,.51),(.27,.61),(.20,.64))), (1, ((.31,.59),(.75,.56))),
        (1, ((.33,.71),(.70,.69))), (2, ((.53,.51),(.53,.84))),
        (1, ((.19,.85),(.81,.83))),
    ),
    "久": (
        (3, ((.45,.20),(.35,.39),(.20,.53))),
        (5, ((.40,.32),(.65,.30),(.57,.47),(.45,.64),(.25,.81))),
        (4, ((.52,.54),(.66,.72),(.83,.83))),
    ),
}
BOARDS = {
    "write-ta-jiu": ("她","久"), "write-hai-gan": ("还","干"),
    "write-kong-xing": ("空","星"), "write-shen": ("身",),
}
QUIZ_STROKES = {
    "quiz-6-a": STROKES["还"][4:],
    "quiz-6-b": STROKES["还"][:3]+STROKES["还"][4:5],
    "quiz-6-c": STROKES["还"][:4],
}
SPOT_PAIRS = (
    ((.35,.40),(.65,.40)), ((.29,.56),(.71,.56)),
    ((.37,.71),(.63,.71)), ((.45,.80),(.55,.80)),
)


def glyph(draw, strokes, x, y, size, last=False):
    draw.rounded_rectangle((x,y,x+size,y+size),radius=size*.06,fill="#fff9ec",outline=LINE,width=2)
    for start in range(4,size-4,11):
        end=min(start+5,size-4)
        draw.line((x+start,y+size/2,x+end,y+size/2),fill=LINE)
        draw.line((x+size/2,y+start,x+size/2,y+end),fill=LINE)
    width=max(2,round(size*.044))
    for index,(_,path) in enumerate(strokes):
        ink=ACTIVE if last and index==len(strokes)-1 else PINE
        points=[(x+u*size,y+v*size) for u,v in path]
        draw.line(points,fill=ink,width=width,joint="curve")
        radius=width/2
        for px,py in (points[0],points[-1]):
            draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill=ink)


def writing_board(characters):
    row_height=198
    height=max(275,row_height*len(characters))
    art=Image.new("RGB",(750,height),PAPER)
    draw=ImageDraw.Draw(art)
    for row,char in enumerate(characters):
        y=14+row*row_height
        strokes=STROKES[char]
        glyph(draw,strokes,25,y+6,147)
        for n in range(len(strokes)):
            glyph(draw,strokes[:n+1],201+n%6*86,y+n//6*88,78,True)
    return art


def spot_locations(count):
    if count not in (6,7,8):
        raise ValueError("the paper models compare six, seven and eight")
    paired=tuple(spot for pair in SPOT_PAIRS[:count//2] for spot in pair)
    return paired+((.50,.34),) if count%2 else paired


def paper_beetle(count, landscape=False):
    width,height=(480,310) if landscape else (300,300)
    art=Image.new("RGB",(width,height),PAPER)
    draw=ImageDraw.Draw(art)
    x=(width-height)/2
    draw.rounded_rectangle((x+12,12,x+height-12,height-12),radius=22,fill="#fff9ec",outline=LINE,width=2)
    draw.ellipse((x+.35*height,.11*height,x+.65*height,.38*height),fill=PINE)
    draw.ellipse((x+.19*height,.27*height,x+.81*height,.89*height),fill="#e16e48",outline=PINE,width=4)
    radius=.032*height
    for u,v in spot_locations(count):
        cx,cy=x+u*height,v*height
        draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=PINE)
    return art


def build(destination):
    destination.mkdir(parents=True,exist_ok=True)
    for key,chars in BOARDS.items():
        writing_board(chars).save(destination/(key+".png"),optimize=True)
    for key,count in (("quiz-3-a",6),("quiz-3-b",8),("quiz-3-c",7)):
        paper_beetle(count).save(destination/(key+".png"),optimize=True)
    seven=paper_beetle(7,landscape=True)
    seven.save(destination/"seven-spots-board.png",optimize=True)
    seven.crop((126,33,354,281)).save(destination/"hop-spots.png",optimize=True)
    for key,strokes in QUIZ_STROKES.items():
        art=Image.new("RGB",(300,300),PAPER)
        glyph(ImageDraw.Draw(art),strokes,20,20,260)
        art.save(destination/(key+".png"),optimize=True)


if __name__ == "__main__":
    build(Path(__file__).with_name("assets"))

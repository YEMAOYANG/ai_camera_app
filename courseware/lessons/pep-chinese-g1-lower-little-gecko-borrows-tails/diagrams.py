"""Draw seven textbook glyphs and exact choices for the walking radical."""
from pathlib import Path

from PIL import Image, ImageDraw


PAPER, GRID, INK, ACTIVE = "#fff2da", "#d8bb8b", "#28473c", "#ba512e"
WALK = (
    (4, ((.20,.24),(.28,.35))),
    (5, ((.15,.46),(.30,.44),(.25,.55),(.31,.62),(.25,.72))),
    (4, ((.14,.75),(.23,.72),(.34,.77),(.53,.83),(.73,.84),(.90,.80))),
)
RUN = (
    (1, ((.23,.26),(.55,.24))), (2, ((.38,.16),(.38,.47))),
    (1, ((.16,.47),(.61,.45))), (2, ((.38,.45),(.38,.70))),
    (1, ((.39,.58),(.57,.56))), (3, ((.27,.57),(.23,.71),(.15,.83))),
    (4, ((.25,.70),(.38,.77),(.56,.82),(.76,.83),(.90,.79))),
)

# GF 0023—2020 printed pages 19, 21, 27, 35, 121, and 180.
STROKES = {
    "向": (
        (3, ((.49,.17),(.41,.32))), (2, ((.25,.34),(.26,.86))),
        (5, ((.25,.34),(.76,.31),(.75,.81),(.71,.87),(.65,.81))),
        (2, ((.39,.47),(.40,.71))), (5, ((.39,.47),(.61,.45),(.60,.70))),
        (1, ((.40,.68),(.60,.66))),
    ),
    "边": (
        (5, ((.43,.37),(.77,.35),(.75,.61),(.72,.70),(.65,.65))),
        (3, ((.58,.24),(.56,.47),(.49,.61),(.39,.71))),
        *WALK,
    ),
    "行": (
        (3, ((.38,.20),(.28,.33),(.17,.41))),
        (3, ((.39,.38),(.29,.52),(.17,.58))),
        (2, ((.30,.51),(.30,.85))),
        (1, ((.46,.26),(.79,.24))), (1, ((.40,.46),(.87,.44))),
        (2, ((.67,.45),(.66,.78),(.62,.85),(.55,.79))),
    ),
    "草": (
        (1, ((.17,.27),(.83,.25))), (2, ((.36,.16),(.37,.36))), (2, ((.66,.15),(.65,.35))),
        (2, ((.32,.40),(.33,.65))), (5, ((.32,.40),(.70,.38),(.69,.65))),
        (1, ((.33,.51),(.69,.49))), (1, ((.33,.63),(.69,.61))),
        (1, ((.19,.73),(.84,.70))), (2, ((.51,.63),(.51,.90))),
    ),
    "赶": (
        *RUN,
        (1, ((.61,.29),(.84,.27))), (1, ((.55,.48),(.90,.46))),
        (2, ((.73,.28),(.73,.69))),
    ),
    "过": (
        (1, ((.37,.40),(.84,.38))), (2, ((.67,.22),(.66,.66),(.61,.72),(.55,.66))),
        (4, ((.43,.50),(.51,.59))),
        *WALK,
    ),
    "找": (
        (1, ((.15,.39),(.43,.36))), (2, ((.30,.19),(.29,.79),(.26,.83),(.20,.78))),
        (1, ((.14,.60),(.42,.49))), (1, ((.43,.40),(.85,.34))),
        (5, ((.62,.16),(.64,.46),(.70,.65),(.83,.81),(.88,.82),(.90,.70))),
        (3, ((.82,.47),(.72,.65),(.59,.77),(.45,.83))), (4, ((.74,.19),(.81,.27))),
    ),
}
BOARDS = {
    "write-xiang-xing":("向","行"), "write-bian-guo":("边","过"),
    "write-cao-zhao":("草","找"), "write-gan":("赶",),
}
CHOICES = {"quiz-6-a":STROKES["赶"][7:],"quiz-6-b":WALK,"quiz-6-c":RUN}


def glyph(draw, strokes, x, y, side, last=False):
    draw.rounded_rectangle((x,y,x+side,y+side),radius=side*.06,fill="#fff9eb",outline=GRID,width=2)
    for start in range(4,side-4,11):
        end=min(start+5,side-4)
        draw.line((x+start,y+side/2,x+end,y+side/2),fill=GRID)
        draw.line((x+side/2,y+start,x+side/2,y+end),fill=GRID)
    width=max(2,round(side*.043))
    for i,(_,path) in enumerate(strokes):
        color=ACTIVE if last and i==len(strokes)-1 else INK
        points=[(x+a*side,y+b*side) for a,b in path]
        draw.line(points,fill=color,width=width,joint="curve")
        radius=width/2
        for px,py in (points[0],points[-1]):
            draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill=color)


def writing_board(chars):
    row_height=198
    art=Image.new("RGB",(750,max(265,row_height*len(chars))),PAPER)
    draw=ImageDraw.Draw(art)
    for row,char in enumerate(chars):
        top=14+row*row_height
        strokes=STROKES[char]
        glyph(draw,strokes,25,top+6,147)
        for n in range(len(strokes)):
            glyph(draw,strokes[:n+1],201+n%6*86,top+n//6*88,78,True)
    return art


def radical_choice(key):
    art=Image.new("RGB",(300,300),PAPER)
    glyph(ImageDraw.Draw(art),CHOICES[key],20,20,260)
    return art


def build(destination):
    destination.mkdir(parents=True,exist_ok=True)
    for key,chars in BOARDS.items():
        writing_board(chars).save(destination/(key+".png"),optimize=True)
    for key in CHOICES:
        radical_choice(key).save(destination/(key+".png"),optimize=True)


if __name__=="__main__":
    build(Path(__file__).with_name("assets"))

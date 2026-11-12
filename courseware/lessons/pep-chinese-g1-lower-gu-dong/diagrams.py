"""Draw the seven textbook characters and the last-dot picture choices."""
from pathlib import Path

from PIL import Image, ImageDraw


PAPER, GRID, INK, ACCENT = "#fff1d8", "#d8bb8b", "#28493c", "#b74f2e"

# GF 0023—2020 printed pages 10, 23, 51, 72, 100, 230 and 277.
STROKES = {
    "吓": (
        (2, ((.16,.38),(.18,.65))), (5, ((.16,.38),(.38,.37),(.37,.65))),
        (1, ((.18,.63),(.37,.62))), (1, ((.43,.28),(.86,.26))),
        (2, ((.59,.29),(.59,.85))), (4, ((.66,.43),(.76,.51),(.83,.58))),
    ),
    "怕": (
        (4, ((.21,.40),(.18,.53))), (4, ((.32,.38),(.39,.45))),
        (2, ((.28,.21),(.28,.86))), (3, ((.62,.21),(.56,.36),(.49,.41))),
        (2, ((.45,.40),(.46,.83))), (5, ((.45,.40),(.80,.38),(.79,.82))),
        (1, ((.46,.59),(.79,.57))), (1, ((.46,.79),(.79,.77))),
    ),
    "没": (
        (4, ((.19,.20),(.25,.28))), (4, ((.14,.42),(.20,.51))),
        (1, ((.13,.73),(.29,.61))), (3, ((.47,.25),(.47,.43),(.38,.52))),
        (5, ((.47,.25),(.66,.23),(.65,.43),(.69,.46),(.80,.45))),
        (5, ((.37,.56),(.75,.54),(.64,.69),(.49,.80),(.32,.86))),
        (4, ((.45,.61),(.57,.73),(.73,.82),(.87,.86))),
    ),
    "到": (
        (1, ((.18,.25),(.58,.23))),
        (5, ((.38,.25),(.24,.43),(.52,.40))), (4, ((.49,.34),(.57,.45))),
        (1, ((.20,.55),(.56,.53))), (2, ((.38,.49),(.38,.76))),
        (1, ((.15,.79),(.58,.72))), (2, ((.68,.34),(.68,.67))),
        (2, ((.83,.19),(.83,.76),(.81,.84),(.75,.79))),
    ),
    "为": (
        (4, ((.28,.20),(.35,.29))), (3, ((.53,.18),(.48,.45),(.35,.67),(.19,.81))),
        (5, ((.25,.40),(.79,.38),(.77,.71),(.73,.82),(.66,.87),(.59,.79))),
        (4, ((.53,.55),(.60,.61),(.66,.68))),
    ),
    "家": (
        (4, ((.46,.14),(.53,.22))), (4, ((.21,.30),(.18,.42))),
        (5, ((.23,.31),(.81,.29),(.76,.42))), (1, ((.31,.44),(.71,.42))),
        (3, ((.54,.43),(.43,.54),(.27,.61))), (5, ((.46,.52),(.54,.62),(.57,.75),(.53,.86),(.46,.81))),
        (3, ((.53,.61),(.39,.70),(.24,.75))), (3, ((.55,.71),(.43,.79),(.22,.86))),
        (3, ((.71,.51),(.65,.61),(.57,.66))), (4, ((.62,.63),(.71,.75),(.85,.82))),
    ),
    "象": (
        (3, ((.42,.15),(.32,.28),(.22,.35))),
        (5, ((.38,.24),(.63,.22),(.55,.33))), (2, ((.27,.37),(.29,.52))),
        (5, ((.27,.37),(.71,.35),(.69,.52))), (1, ((.29,.50),(.69,.49))),
        (3, ((.52,.36),(.43,.52),(.29,.60))),
        (5, ((.46,.50),(.53,.59),(.56,.73),(.55,.84),(.51,.89),(.44,.83))),
        (3, ((.52,.59),(.41,.69),(.24,.74))), (3, ((.55,.70),(.41,.80),(.20,.86))),
        (3, ((.70,.54),(.64,.62),(.56,.68))), (4, ((.61,.65),(.71,.77),(.86,.85))),
    ),
}
BOARDS = {
    "write-xia-pa": ("吓","怕"), "write-mei-dao": ("没","到"),
    "write-wei-jia": ("为","家"), "write-xiang": ("象",),
}
DOTS = {
    "quiz-6-a": ((.18,.70),(.21,.75),(.25,.80)),
    "quiz-6-b": ((.85,.52),(.90,.59),(.93,.67)),
    "quiz-6-c": STROKES["为"][-1][1],
}


def glyph(draw, strokes, x, y, side, accent=False):
    draw.rounded_rectangle((x,y,x+side,y+side),radius=side*.06,fill="#fff9eb",outline=GRID,width=2)
    for start in range(4,side-4,11):
        end=min(start+5,side-4)
        draw.line((x+start,y+side/2,x+end,y+side/2),fill=GRID)
        draw.line((x+side/2,y+start,x+side/2,y+end),fill=GRID)
    width=max(2,round(side*.043))
    for i,(_,path) in enumerate(strokes):
        color=ACCENT if accent and i==len(strokes)-1 else INK
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


def last_dot_card(key):
    art=Image.new("RGB",(300,300),PAPER)
    glyph(ImageDraw.Draw(art),STROKES["为"][:3]+((4,DOTS[key]),),20,20,260,True)
    return art


def build(destination):
    destination.mkdir(parents=True,exist_ok=True)
    for key,chars in BOARDS.items():
        writing_board(chars).save(destination/(key+".png"),optimize=True)
    for key in DOTS:
        last_dot_card(key).save(destination/(key+".png"),optimize=True)


if __name__=="__main__":
    build(Path(__file__).with_name("assets"))

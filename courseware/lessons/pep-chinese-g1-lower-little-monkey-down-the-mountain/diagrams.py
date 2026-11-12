"""Draw the seven verified stroke orders and the lesson's exact quiz variants."""
from pathlib import Path

from PIL import Image, ImageDraw


PAPER = "#fff2d9"
GRID = "#d9b880"
PINE = "#27473b"
ACTIVE = "#b14d29"

# GF 0023—2020 printed pages 15, 30, 34, 87, 91, 218 and 283.
# Each entry has a standard stroke class (horizontal 1 through turn 5) and its path.
STROKES = {
    "高": (
        (4, ((.47,.16),(.54,.23))), (1, ((.20,.28),(.80,.26))),
        (2, ((.34,.37),(.35,.49))), (5, ((.34,.37),(.66,.35),(.64,.49))),
        (1, ((.35,.47),(.64,.46))), (2, ((.24,.55),(.25,.86))),
        (5, ((.24,.55),(.77,.53),(.76,.82),(.72,.87),(.66,.81))),
        (2, ((.38,.64),(.39,.77))), (5, ((.38,.64),(.62,.63),(.61,.77))),
        (1, ((.39,.75),(.61,.74))),
    ),
    "兴": (
        (4, ((.29,.25),(.35,.35))), (4, ((.46,.20),(.51,.29))),
        (3, ((.69,.21),(.65,.31),(.58,.40))), (1, ((.20,.48),(.80,.46))),
        (3, ((.41,.60),(.34,.73),(.24,.80))), (4, ((.58,.61),(.70,.70),(.77,.80))),
    ),
    "着": (
        (4, ((.36,.16),(.41,.24))), (3, ((.62,.14),(.56,.25))),
        (1, ((.27,.30),(.73,.28))), (1, ((.32,.39),(.68,.37))),
        (1, ((.18,.49),(.81,.47))), (3, ((.49,.48),(.41,.63),(.29,.77),(.17,.82))),
        (2, ((.43,.56),(.44,.86))), (5, ((.43,.56),(.70,.54),(.69,.86))),
        (1, ((.44,.65),(.69,.64))), (1, ((.44,.73),(.69,.72))),
        (1, ((.44,.84),(.69,.82))),
    ),
    "往": (
        (3, ((.35,.20),(.28,.31),(.18,.38))), (3, ((.37,.36),(.29,.49),(.17,.56))),
        (2, ((.29,.49),(.29,.84))), (4, ((.56,.20),(.64,.29))),
        (1, ((.44,.37),(.79,.35))), (1, ((.47,.54),(.77,.52))),
        (2, ((.62,.36),(.62,.76))), (1, ((.40,.78),(.86,.75))),
    ),
    "瓜": (
        (3, ((.73,.20),(.57,.28),(.31,.34))),
        (3, ((.34,.33),(.32,.55),(.25,.71),(.15,.82))),
        (5, ((.47,.32),(.46,.76),(.59,.68))),
        (4, ((.56,.60),(.62,.72))),
        (4, ((.63,.27),(.67,.50),(.73,.65),(.85,.81),(.92,.82))),
    ),
    "兔": (
        (3, ((.44,.16),(.34,.32),(.23,.39))),
        (5, ((.40,.24),(.64,.22),(.56,.36))),
        (2, ((.28,.40),(.29,.57))), (5, ((.28,.40),(.72,.38),(.70,.56))),
        (1, ((.29,.55),(.70,.54))),
        (3, ((.49,.36),(.47,.53),(.40,.70),(.29,.81),(.16,.86))),
        (5, ((.56,.56),(.55,.76),(.57,.83),(.66,.85),(.81,.83),(.85,.78),(.86,.71))),
        (4, ((.65,.65),(.71,.69),(.76,.75))),
    ),
    "进": (
        (1, ((.40,.28),(.77,.26))), (1, ((.37,.47),(.84,.44))),
        (3, ((.53,.17),(.53,.46),(.49,.60),(.43,.69))),
        (2, ((.68,.15),(.68,.70))), (4, ((.20,.24),(.27,.34))),
        (5, ((.15,.46),(.29,.44),(.23,.57),(.29,.62),(.23,.73))),
        (4, ((.15,.76),(.24,.73),(.34,.76),(.48,.81),(.67,.82),(.90,.79))),
    ),
}
BOARDS = {
    "write-gao-xing": ("高","兴"),
    "write-zhe-wang": ("着","往"),
    "write-gua-tu": ("瓜","兔"),
    "write-jin": ("进",),
}
WRONG_DOTS = {
    "quiz-5-b": ((.20,.62),(.26,.68),(.29,.73)),
    "quiz-5-c": ((.78,.17),(.83,.23),(.87,.28)),
}


def grid(draw, x, y, side):
    draw.rounded_rectangle((x,y,x+side,y+side), radius=side*.065, fill="#fff9ec", outline=GRID, width=2)
    for pos in range(5,side-5,12):
        end=min(pos+6,side-5)
        draw.line((x+pos,y+side/2,x+end,y+side/2),fill=GRID,width=1)
        draw.line((x+side/2,y+pos,x+side/2,y+end),fill=GRID,width=1)


def write(draw, strokes, x, y, side, *, accent):
    grid(draw,x,y,side)
    width=max(2,round(side*.044))
    for index,(_,path) in enumerate(strokes):
        ink=ACTIVE if accent and index==len(strokes)-1 else PINE
        points=[(x+u*side,y+v*side) for u,v in path]
        draw.line(points,fill=ink,width=width,joint="curve")
        radius=width/2
        for px,py in (points[0],points[-1]):
            draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill=ink)


def stroke_board(characters):
    width=790
    row_height=215 if len(characters)==2 else 324
    art=Image.new("RGB",(width,2*row_height if len(characters)==2 else row_height),PAPER)
    draw=ImageDraw.Draw(art)
    for row,character in enumerate(characters):
        strokes=STROKES[character]
        write(draw,strokes,24,row*row_height+(row_height-150)//2,150,accent=False)
        for index in range(len(strokes)):
            column=index%6
            line=index//6
            write(draw,strokes[:index+1],204+column*94,row*row_height+20+line*94,83,accent=True)
    return art


def rabbit_choice(key):
    art=Image.new("RGB",(308,308),PAPER)
    draw=ImageDraw.Draw(art)
    strokes=STROKES["兔"]
    if key in WRONG_DOTS:
        strokes=(*strokes[:-1],(4,WRONG_DOTS[key]))
    write(draw,strokes,21,21,266,accent=True)
    return art


def balloon_choice(key):
    # Each card has the same reference on the right. Only the size or shape of
    # the orange balloon changes, so both spoken features are needed.
    spans={"quiz-4-a":(40,83),"quiz-4-b":(66,66),"quiz-4-c":(158,158)}
    art=Image.new("RGB",(330,230),PAPER)
    draw=ImageDraw.Draw(art)
    draw.line((165,35,165,194),fill=GRID,width=2)
    for cx,color,shape in ((81,"#de7848",spans[key]),(244,"#879c8d",(108,108))):
        w,h=shape
        cy=102
        x,y=cx-w/2,cy-h/2
        draw.ellipse((x,y,x+w,y+h),fill=color,outline=PINE,width=3)
        draw.arc((x+w*.18,y+h*.15,x+w*.72,y+h*.76),196,261,fill="#fff0bf",width=5)
        bottom=cy+h/2
        draw.polygon(((cx,bottom-2),(cx-6,bottom+8),(cx+6,bottom+8)),fill=color)
        draw.line(((cx,bottom+8),(cx+6,bottom+23),(cx-3,bottom+37)),fill=PINE,width=2)
    return art


def build(destination):
    destination.mkdir(parents=True,exist_ok=True)
    for key,characters in BOARDS.items():
        stroke_board(characters).save(destination/(key+".png"),optimize=True)
    for choice in "abc":
        for q,draw in ((4,balloon_choice),(5,rabbit_choice)):
            key=f"quiz-{q}-{choice}"
            draw(key).save(destination/(key+".png"),optimize=True)


if __name__ == "__main__":
    build(Path(__file__).with_name("assets"))

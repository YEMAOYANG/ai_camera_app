"""Make exact paper-writing guides and the new outside-first picture choices."""
from pathlib import Path

from PIL import Image, ImageDraw


PAPER, GRID, INK, MARK = "#fff3dd", "#dbbc8b", "#25483c", "#ba502c"

# GF 0023—2020 printed pages 4, 16, 20, 103, 144, and 163.
STROKES = {
    "巾": (
        (2, ((.26,.34),(.26,.70))),
        (5, ((.26,.34),(.75,.32),(.73,.66),(.70,.71),(.65,.65))),
        (2, ((.50,.17),(.50,.86))),
    ),
    "洗": (
        (4, ((.19,.21),(.25,.29))), (4, ((.14,.43),(.21,.51))),
        (1, ((.13,.72),(.29,.59))), (3, ((.52,.22),(.48,.36),(.43,.42))),
        (1, ((.49,.34),(.79,.32))), (2, ((.64,.17),(.64,.51))),
        (1, ((.39,.53),(.87,.51))), (3, ((.57,.53),(.54,.69),(.47,.79),(.36,.85))),
        (5, ((.69,.52),(.68,.73),(.71,.79),(.84,.79),(.89,.74),(.90,.65))),
    ),
    "房": (
        (4, ((.50,.14),(.55,.23))), (5, ((.30,.29),(.75,.27),(.73,.43))),
        (1, ((.30,.43),(.73,.42))), (3, ((.30,.29),(.29,.56),(.24,.70),(.16,.82))),
        (4, ((.56,.45),(.60,.51))), (1, ((.38,.57),(.83,.55))),
        (5, ((.54,.67),(.74,.65),(.72,.81),(.67,.86),(.60,.81))),
        (3, ((.55,.56),(.53,.68),(.46,.77),(.36,.85))),
    ),
    "老": (
        (1, ((.31,.28),(.66,.26))), (2, ((.49,.17),(.49,.46))),
        (1, ((.20,.47),(.83,.44))),
        (3, ((.72,.21),(.61,.41),(.49,.55),(.34,.66),(.18,.72))),
        (3, ((.74,.55),(.65,.65),(.55,.70))),
        (5, ((.53,.56),(.52,.76),(.55,.83),(.67,.85),(.80,.82),(.83,.77),(.84,.68))),
    ),
    "看": (
        (3, ((.71,.15),(.54,.21),(.31,.25))), (1, ((.29,.34),(.72,.32))),
        (1, ((.22,.45),(.80,.43))), (3, ((.46,.23),(.43,.45),(.35,.59),(.20,.68))),
        (2, ((.42,.54),(.43,.87))), (5, ((.42,.54),(.69,.52),(.68,.87))),
        (1, ((.43,.63),(.68,.62))), (1, ((.43,.73),(.68,.72))),
        (1, ((.43,.84),(.68,.83))),
    ),
    "包": (
        (3, ((.40,.15),(.34,.28),(.24,.38))),
        (5, ((.37,.25),(.80,.23),(.76,.57),(.72,.63),(.65,.59))),
        (5, ((.35,.39),(.64,.38),(.62,.54))),
        (1, ((.35,.54),(.62,.52))),
        (5, ((.35,.54),(.35,.74),(.39,.80),(.54,.82),(.78,.81),(.82,.77),(.84,.68))),
    ),
}
OUTSIDE_COUNTS = {"房":4, "老":4, "看":4, "包":2}
WRITE_BOARDS = {
    "write-towel-wash": ("巾", "洗"),
    "write-left-surround": ("房", "老", "看"),
    "write-right-surround": ("包",),
}
QUIZ_STROKES = {
    "quiz-4-a": STROKES["房"][4:],
    "quiz-4-b": STROKES["房"][:4],
    "quiz-4-c": STROKES["房"][:1] + STROKES["房"][4:6],
}


def write(draw, strokes, x, y, size, highlight=()):
    draw.rounded_rectangle((x,y,x+size,y+size),radius=size*.065,fill="#fff9eb",outline=GRID,width=2)
    for pos in range(4,size-4,11):
        end=min(pos+5,size-4)
        draw.line((x+pos,y+size/2,x+end,y+size/2),fill=GRID)
        draw.line((x+size/2,y+pos,x+size/2,y+end),fill=GRID)
    width=max(2,round(size*.044))
    for index,(_,path) in enumerate(strokes):
        color=MARK if index in highlight else INK
        points=[(x+u*size,y+v*size) for u,v in path]
        draw.line(points,fill=color,width=width,joint="curve")
        radius=width/2
        for px,py in (points[0],points[-1]):
            draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill=color)


def teaching_board(characters):
    step_mode=characters==WRITE_BOARDS["write-towel-wash"]
    row_height=200 if step_mode else 168
    art=Image.new("RGB",(720,max(270,row_height*len(characters)+12)),PAPER)
    draw=ImageDraw.Draw(art)
    for row,char in enumerate(characters):
        strokes=STROKES[char]
        y=11+row*row_height
        write(draw,strokes,24,y+8,145)
        if step_mode:
            for n in range(len(strokes)):
                write(draw,strokes[:n+1],194+n%6*84,y+n//6*86,77,(n,))
        else:
            outer=OUTSIDE_COUNTS[char]
            write(draw,strokes[:outer],236,y+8,145,range(outer))
            write(draw,strokes,451,y+8,145,range(outer,len(strokes)))
    return art


def quiz_card(key):
    art=Image.new("RGB",(300,300),PAPER)
    write(ImageDraw.Draw(art),QUIZ_STROKES[key],18,18,264)
    return art


def build(destination):
    destination.mkdir(parents=True,exist_ok=True)
    for key,chars in WRITE_BOARDS.items():
        teaching_board(chars).save(destination/(key+".png"),optimize=True)
    for key in QUIZ_STROKES:
        quiz_card(key).save(destination/(key+".png"),optimize=True)


if __name__ == "__main__":
    build(Path(__file__).with_name("assets"))

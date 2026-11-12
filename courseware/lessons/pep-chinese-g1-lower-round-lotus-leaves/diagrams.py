"""Compose lotus story cards and exact spatial, visual, and stroke diagrams."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Songti.ttc"
PINE, CREAM, ORANGE, SAGE = "#24453c", "#fff1d7", "#bd572c", "#85a487"

TURN = ((.26,.36),(.63,.31),(.59,.53),(.60,.65),(.68,.70),(.83,.70))
HOOK = (*TURN,(.86,.67),(.88,.53))
FOLD = TURN[:3]


def read(root, name, asset=True):
    path=root/("assets" if asset else "art-source")/(name+".png")
    with Image.open(path) as image:
        return image.convert("RGBA")


def board(size):
    return Image.new("RGBA",size,CREAM)


def paste(canvas, sprite, position, size):
    item=sprite.copy()
    item.thumbnail(size,Image.Resampling.LANCZOS)
    x,y=position
    canvas.alpha_composite(item,(round(x-item.width/2),round(y-item.height/2)))


def glyph(draw, text, position, size):
    draw.text(position,text,font=ImageFont.truetype(FONT,size),fill=PINE,anchor="mm")


def row(left, right, *, connect=True):
    out=board((605,296))
    paste(out,left,(145,148),(276,277))
    paste(out,right,(459,148),(276,277))
    if connect:
        draw=ImageDraw.Draw(out)
        draw.line((288,147,312,147),fill=ORANGE,width=6)
        draw.polygon(((315,147),(302,138),(302,156)),fill=ORANGE)
    return out


def grid(items):
    out=board((607,582))
    for idx,item in enumerate(items):
        y,x=divmod(idx,2)
        paste(out,item,(151+303*x,145+290*y),(287,274))
    return out


def field(draw, left, top, size):
    draw.rounded_rectangle((left,top,left+size,top+size),radius=12,outline=SAGE,width=3)
    draw.line((left+size/2,top+4,left+size/2,top+size-4),fill="#bfd0a8",width=2)
    draw.line((left+4,top+size/2,left+size-4,top+size/2),fill="#bfd0a8",width=2)


def curve(draw, points, left, top, span, thickness):
    pixels=[(round(left+x*span),round(top+y*span)) for x,y in points]
    draw.line(pixels,fill=ORANGE,width=thickness,joint="curve")
    r=thickness//2
    for x,y in (pixels[0],pixels[-1]):
        draw.ellipse((x-r,y-r,x+r,y+r),fill=ORANGE)


def writing(characters, turn=False):
    out=board((692,425)); draw=ImageDraw.Draw(out)
    for i, char in enumerate(characters):
        left=17+i*226
        field(draw,left,23,205)
        glyph(draw,char,(left+103,132),167)
        field(draw,left+54,252,96)
        if turn and i==0:
            curve(draw,TURN,left+54,252,96,8)
    return out


def stroke_picture(stroke):
    out=board((439,297)); draw=ImageDraw.Draw(out)
    field(draw,97,20,245)
    curve(draw,stroke,97,20,245,17)
    return out


def propped(sprite, *, showcase=False):
    out=board((425,295)); draw=ImageDraw.Draw(out)
    draw.rounded_rectangle((10,12,414,280),radius=31,fill="#e2e9cc")
    if showcase:
        draw.rounded_rectangle((303,32,373,105),radius=9,fill="#f0b974")
        draw.ellipse((318,42,358,82),fill="#fbebc8")
    draw.rounded_rectangle((44,217,380,256),radius=13,fill="#d2a66e")
    paste(out,sprite,(209,151),(262,182))
    return out


def compare_fish(leaf, fish, place):
    out=board((443,319)); draw=ImageDraw.Draw(out)
    draw.rounded_rectangle((9,9,434,309),radius=24,fill="#d8e8d6")
    draw.rectangle((12,238,430,284),fill="#a7cfd1")
    paste(out,leaf,(194,158),(235,210))
    positions={"under":(216,228),"above":(211,51),"beside":(351,122)}
    paste(out,fish,positions[place],(101,76))
    return out


def transparent(leaf, color):
    out=board((405,320)); draw=ImageDraw.Draw(out)
    draw.rounded_rectangle((10,11,394,304),radius=25,fill="#dce9d1")
    paste(out,leaf,(207,162),(250,240))
    overlay=Image.new("RGBA",out.size)
    cover=ImageDraw.Draw(overlay)
    cover.rounded_rectangle((134,48,285,240),radius=17,fill=color,outline="#466772",width=5)
    cover.line((153,83,186,59),fill="#fff9e3",width=4)
    out.alpha_composite(overlay)
    return out


def frog_frame(sprite, jumps=False):
    out=board((280,290)); draw=ImageDraw.Draw(out)
    draw.rounded_rectangle((8,7,272,279),radius=22,fill="#e0edda")
    draw.ellipse((49,225,231,258),fill="#769d79")
    paste(out,sprite,(140,124 if jumps else 157),(166,186 if jumps else 151))
    return out


def render(root=ROOT):
    def save(name,out):
        out.save(root/"assets"/(name+".png"),optimize=True)
    def art(name): return read(root,name)
    def source(name): return read(root,name,False)
    drop,fly,frog,fish=[art(name+"-icon") for name in ("drop","fly","frog","fish")]
    cradle,pad,stage,shade=[art(name+"-icon") for name in ("cradle","pad","stage","shade")]
    scene_drop,scene_fly,scene_frog,scene_fish=[art(name) for name in ("drop-on-leaf","dragonfly-on-leaf","frog-on-leaf","fish-under-leaf")]
    leaf=source("lotus-canopy")
    save("frog-fish",row(scene_frog,scene_fish,connect=False))
    save("motion-grid",grid([scene_drop,scene_fly,scene_frog,scene_fish]))
    cover=board((610,359)); draw=ImageDraw.Draw(cover)
    draw.rounded_rectangle((16,16,594,344),radius=29,fill="#e3ebd1")
    for i,sprite in enumerate((drop,fly,frog,fish)):
        paste(cover,sprite,(92+i*141,99),(107,102))
    paste(cover,art("pond-cart"),(307,254),(194,127))
    save("role-start",cover)
    cover=board((596,351)); paste(cover,scene_fly,(240,178),(381,319))
    paste(cover,art("pond-marble"),(478,259),(104,104))
    save("marble-start",cover)
    save("writing-one",writing("机台伞"))
    save("writing-two",writing("朵美唱",turn=True))
    save("reading-cards",grid([row(drop,cradle),row(fly,pad),row(frog,stage),row(fish,shade)]))
    for suffix,obj in zip("abc",(shade,cradle,stage)):
        save(f"quiz-1-{suffix}",propped(obj))
    for suffix,obj in zip("abc",(stage,cradle,pad)):
        save(f"quiz-2-{suffix}",propped(obj,showcase=True))
    for suffix,pos in zip("abc",("under","above","beside")):
        save(f"quiz-3-{suffix}",compare_fish(leaf,fish,pos))
    for suffix,color in zip("abc",("#ecd6ad","#b6e8ef49","#3b6751")):
        save(f"quiz-4-{suffix}",transparent(leaf,color))
    for suffix,name in zip("abc",("orange-ball","orange-ribbon","violet-ball")):
        save(f"quiz-5-{suffix}",propped(source(name)))
    for suffix,shape in zip("abc",(TURN,HOOK,FOLD)):
        save(f"quiz-6-{suffix}",stroke_picture(shape))
    silent=frog_frame(source("frog-silent"))
    singing=frog_frame(source("frog-singing"))
    jumping=frog_frame(source("frog-jump"),jumps=True)
    for suffix,(a,b) in zip("abc",((singing,silent),(silent,singing),(silent,jumping))):
        save(f"quiz-7-{suffix}",row(a,b))


if __name__ == "__main__":
    render()

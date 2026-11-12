"""Compose original sprites into exact lesson comparisons and stroke diagrams."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
CREAM, PINE, ORANGE = "#fff1d5", "#23453a", "#bd5529"

STROKES = {
    "来": (
        ((29,25),(72,24)), ((37,32),(43,41)), ((63,30),(56,41)),
        ((17,48),(85,47)), ((51,13),(50,90)), ((48,51),(37,68),(19,80)),
        ((52,53),(66,69),(86,79)),
    ),
    "半": (
        ((31,19),(39,32)), ((69,16),(59,32)), ((29,40),(72,39)),
        ((19,61),(83,59)), ((51,12),(50,91)),
    ),
    "你": (
        ((31,11),(25,29),(12,46)), ((24,34),(23,86)), ((56,13),(49,32),(41,44)),
        ((50,36),(89,36),(81,47)), ((66,43),(65,81),(63,89),(53,82)),
        ((54,60),(47,73),(40,80)), ((77,59),(90,77)),
    ),
    "有": (
        ((16,28),(85,25)), ((56,12),(50,36),(37,56),(19,72)),
        ((40,47),(39,90)), ((40,46),(76,45),(75,82),(74,91),(65,84)),
        ((41,59),(74,58)), ((40,73),(74,72)),
    ),
}


def read(root, name, assets=False):
    location = root / ("assets" if assets else "art-source") / (name + ".png")
    with Image.open(location) as value:
        return value.convert("RGBA")


def canvas(size):
    return Image.new("RGBA", size, CREAM)


def paste(frame, source, xy, dimensions, bottom=False):
    tile = source.copy()
    tile.thumbnail(dimensions, Image.Resampling.LANCZOS)
    x, y = xy
    frame.alpha_composite(tile, (round(x - tile.width / 2), round(y - (tile.height if bottom else tile.height / 2))))


def arrow(draw, x, y):
    draw.line((x-12,y,x+9,y), width=5, fill=ORANGE)
    draw.polygon(((x+12,y),(x+4,y-7),(x+4,y+7)), fill=ORANGE)


def row(left, right):
    width, height = 230, 215
    frame = canvas((501, 235))
    for x, tile in ((123,left),(378,right)):
        paste(frame, tile, (x,117), (width,height))
    arrow(ImageDraw.Draw(frame),251,117)
    return frame


def grid(images):
    frame = canvas((499,499))
    for n, image in enumerate(images):
        y,x = divmod(n,2)
        paste(frame,image,(127+245*x,127+245*y),(230,230))
    return frame


def paths(glyphs):
    frame = canvas((780, 432))
    draw = ImageDraw.Draw(frame)

    def show(x, y, size, strokes, current=False):
        draw.rounded_rectangle((x,y,x+size,y+size),radius=9,outline="#8ca68a",width=2)
        draw.line((x+size/2,y+3,x+size/2,y+size-3),fill="#b9c8a1",width=1)
        draw.line((x+3,y+size/2,x+size-3,y+size/2),fill="#b9c8a1",width=1)
        thickness = max(3,size//18)
        for i, stroke in enumerate(strokes,1):
            pixels=[(round(x+a*size/100),round(y+b*size/100)) for a,b in stroke]
            color = ORANGE if current and i==len(strokes) else PINE
            draw.line(pixels,fill=color,width=thickness,joint="curve")
            for px,py in (pixels[0],pixels[-1]):
                radius=thickness//2
                draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill=color)

    for line, glyph in enumerate(glyphs):
        y = 10 + line * 208
        show(14,y,200,STROKES[glyph])
        for i in range(len(STROKES[glyph])):
            show(233+(i%4)*130,y+(i//4)*101,94,STROKES[glyph][:i+1],True)
    return frame


def tones(pictures, labels):
    frame = grid(pictures)
    draw = ImageDraw.Draw(frame)
    font = ImageFont.truetype(FONT, 37)
    for i, label in enumerate(labels):
        y,x = divmod(i,2)
        left,top=22+x*245,199+y*245
        draw.rounded_rectangle((left,top,left+210,top+40),radius=12,fill=CREAM)
        draw.text((left+105,top+19),label,font=font,fill=PINE,anchor="mm")
    return frame


def grow(site, flower, grass, places, bright):
    frame = site.copy()
    w,h=frame.size
    for image,x,y,size in ((flower,*places[0]),(grass,*places[1])):
        if size:
            item = image
            if not bright:
                item = ImageEnhance.Color(image).enhance(.46)
                item = ImageEnhance.Brightness(item).enhance(.89)
            paste(frame,item,(x*w,y*h),(round(w*size),round(h*size)),bottom=True)
    return frame


def rain_roles(big, small, mic, speaker):
    frame=canvas((278,242))
    draw=ImageDraw.Draw(frame)
    draw.rounded_rectangle((4,5,274,236),radius=24,fill="#dceadd")
    paste(frame,big,(72,170),(108,145),bottom=True)
    paste(frame,small,(213,168),(98,110),bottom=True)
    mark_x = 77 if speaker=="big" else 204
    draw.ellipse((mark_x-30,169,mark_x+30,228),fill="#ffda91",outline=ORANGE,width=3)
    paste(frame,mic,(mark_x,198),(41,46))
    return frame


def truck_picture(truck, bridge, *, moving):
    frame=canvas((400,300))
    draw=ImageDraw.Draw(frame)
    draw.rounded_rectangle((4,4,395,295),radius=24,fill="#d3e4df")
    draw.rectangle((10,202,390,266),fill="#889d74")
    draw.line((10,239,389,239),fill="#fff2d3",width=5)
    paste(frame,bridge,(101,200),(141,105),bottom=True)
    paste(frame,truck,(295 if moving else 172,242),(115,95),bottom=True)
    if moving:
        for y in (166,183):
            draw.line((213,y,247,y),fill=ORANGE,width=5)
    return frame


def lantern_picture(lantern, *, showing=True, swing=False):
    frame=canvas((328,300))
    draw=ImageDraw.Draw(frame)
    draw.rounded_rectangle((5,5,322,295),radius=24,fill="#dde8d9")
    draw.polygon([(12,81),(39,51),(291,51),(316,81)],fill="#326055")
    draw.line((165,78,165,115),fill=PINE,width=4)
    if showing:
        image=lantern.rotate(-15,Image.Resampling.BICUBIC,expand=True) if swing else lantern
        paste(frame,image,(184 if swing else 164,184),(110,151))
    if swing:
        draw.arc((125,119,245,239),195,245,fill=ORANGE,width=6)
        draw.arc((170,119,279,239),265,315,fill=ORANGE,width=6)
    return frame


def render(root=ROOT):
    def save(name, image):
        image.save(root/"assets"/(name+".png"),optimize=True)

    def asset(name):
        return read(root,name,True)

    bare, meadow, yard = [read(root,name) for name in ("site-empty","site-green","site-yard")]
    flower, grass, bridge, lantern = [read(root,name) for name in ("flower","grass","stone-bridge","paper-lantern")]
    big, small, mic, truck = [asset(name) for name in ("drop-big","drop-small","rain-mic","rain-truck")]
    a_places=((.45,.79,.38),(.68,.86,.28))
    b_places=((.57,.68,.35),(.76,.76,.26))
    y_places=((.44,.68,.39),(.68,.74,.25))
    path_places=((.63,.82,.38),(.39,.86,.28))
    bare_after=grow(bare,flower,grass,a_places,True)
    meadow_before=grow(meadow,flower,grass,b_places,False)
    meadow_after=grow(meadow,flower,grass,b_places,True)
    yard_before=grow(yard,flower,grass,y_places,False)
    yard_after=grow(yard,flower,grass,y_places,True)
    y_grass=((0,0,0),y_places[1])
    yard_grass=grow(yard,flower,grass,y_grass,True)
    yard_grass_soft=grow(yard,flower,grass,y_grass,False)
    yard_flower=grow(yard,flower,grass,(y_places[0],(0,0,0)),True)
    path_bare=bare.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    path_before=grow(path_bare,flower,grass,path_places,False)
    path_after=grow(path_bare,flower,grass,path_places,True)

    save("empty-station",bare)
    save("green-station",meadow_after)
    save("words-above",tones([asset("cloud-radio"),asset("count-lanterns"),meadow,bare],["点","数","云彩 半空","地方"]))
    save("words-in-talk",tones([asset("ask-scene"),asset("answer-scene"),asset("grow-leaf"),asset("long-ribbon")],
        ["问","回 答","长出","长短"]))
    save("writing-one",paths("来半"))
    save("writing-two",paths("你有"))
    save("pause-example",row(truck_picture(truck,bridge,moving=False),truck_picture(truck,bridge,moving=True)))
    small_talk,big_talk=[rain_roles(big,small,mic,name) for name in ("small","big")]
    save("role-rehearsal",row(small_talk,big_talk))
    save("rain-dialogue",grid([big_talk,small_talk,bare,meadow_before]))
    save("delivery-start",grid([big,small,bare,meadow_before]))
    save("two-endings",grid([meadow_before,meadow_after,bare,bare_after]))

    for name,(left,right) in {
        "grow-choice-a":(yard,yard_grass),"grow-choice-b":(yard_grass_soft,yard_grass),"grow-choice-c":(yard,yard),
        "change-choice-a":(yard,yard_after),"change-choice-b":(yard_before,yard_after),"change-choice-c":(yard,yard_flower),
        "bright-choice-a":(path_bare,path_after),"bright-choice-b":(path_before,path_after),"bright-choice-c":(path_before,path_before),
        "talk-choice-a":(big_talk,small_talk),"talk-choice-b":(small_talk,small_talk),"talk-choice-c":(small_talk,big_talk),
    }.items():
        save(name,row(left,right))

    save("place-choice-a",bare)
    save("place-choice-b",grow(meadow,flower,grass,((0,0,0),b_places[1]),True))
    save("place-choice-c",yard_after)
    still=lantern_picture(lantern)
    swing=lantern_picture(lantern,swing=True)
    no_lantern=lantern_picture(lantern,showing=False)
    save("pause-choice-a",row(still,swing))
    save("pause-choice-b",row(swing,still))
    save("pause-choice-c",row(no_lantern,still))


if __name__ == "__main__":
    render()

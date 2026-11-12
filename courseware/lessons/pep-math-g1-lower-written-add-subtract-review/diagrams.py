"""Render the lesson's exact place-value models and vertical records."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ATLAS = ASSETS / "source/observation-atlas.png"
INK = "#173e35"
CREAM = "#fbefcf"
GREEN = "#47816d"
ORANGE = "#de995d"
RED = "#a13d27"
LINE = "#ae8b64"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


SORT = {
    "s-36-22": (36, "+", 22), "s-39-24": (39, "+", 24),
    "s-68-35": (68, "−", 35), "s-61-23": (61, "−", 23), "s-85-44": (85, "−", 44),
    "s-52-31": (52, "+", 31), "s-48-27": (48, "+", 27),
    "s-77-42": (77, "−", 42), "s-63-29": (63, "−", 29),
}
REPAIR = {
    "copy-plus": (43, "+", 15), "copy-minus": (64, "−", 31),
    "carry-a": (26, "+", 49), "carry-b": (35, "+", 28),
    "borrow-a": (84, "−", 56), "borrow-b": (71, "−", 46),
}
RESULT_TARGETS = (75, 65, 63, 53, 28, 38, 25, 35)


def text(d, pos, value, size, color=INK):
    d.text(pos, str(value), anchor="mm", font=ImageFont.truetype(FONT, size), fill=color)


def panel(size=(560, 330)):
    w, h = size
    im = Image.new("RGBA", size)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((4, 4, w - 5, h - 5), radius=24, fill=CREAM, outline=LINE, width=3)
    return im, d


def stroke(d, x, y, u, *, tens=False, color=None):
    color = color or (GREEN if tens else ORANGE)
    height = u * (10 if tens else 1)
    d.rounded_rectangle((x, y, x + u, y + height), radius=max(1, u // 5), fill=color, outline=INK, width=1)
    if tens:
        for line in range(1, 10):
            yy = y + u * line
            d.line((x + 1, yy, x + u - 1, yy), fill="#e0e2ba")


def stock(d, area, tens, ones, *, crossed=(0, 0), count_label=False):
    assert 0 <= tens <= 9 and 0 <= ones <= 19
    assert 0 <= crossed[0] <= tens and 0 <= crossed[1] <= ones
    left, top, w, h = area
    u = max(3, min(w // 25, h // 13))
    y = top + (h - 10 * u) // 2
    midpoint = left + 16 * u
    d.line((midpoint-u, y-u, midpoint-u, y+11*u), fill=LINE, width=max(1, u // 5))
    for i in range(tens):
        x = left + u + i * int(1.45 * u) + (u // 2 if i >= 5 else 0)
        stroke(d, x, y, u, tens=True)
        if i >= tens - crossed[0]:
            d.line((x - 1, y + u * 10, x + u + 1, y), fill=RED, width=max(2, u // 4))
    for i in range(ones):
        x = midpoint + i % 5 * int(1.43*u)
        yy = y + u + i // 5 * int(1.6*u)
        stroke(d, x, yy, u)
        if i >= ones - crossed[1]:
            d.line((x - 1, yy + u + 1, x + u + 1, yy - 1), fill=RED, width=max(2, u // 4))
    if count_label:
        text(d, (left+w/2, top+10), tens*10+ones, min(40, max(18, w//9)))


def computed(a, sign, b):
    return a+b if sign=="+" else a-b


def needs_mark(a, sign, b):
    return (a%10+b%10 >= 10) if sign=="+" else (a%10 < b%10)


def column_card(a, sign, b, *, answer=None, mark=False, shifted=False, tiny=False):
    w, h = (224, 224) if tiny else (360, 305)
    im, d = panel((w, h))
    tens, ones = int(w*.43), int(w*.71)
    first, second, bar, answer_y = [int(h*v) for v in (.24,.50,.66,.81)]
    font = int(h*(.31 if tiny else .22))
    for x in (tens,ones):
        d.rounded_rectangle((x-font//2-4, int(h*.085), x+font//2+4, int(h*.93)), radius=11, fill="#eadfbd")
    text(d,(tens,first),a//10,font); text(d,(ones,first),a%10,font)
    text(d,(int(w*.15),second),sign,int(font*.8))
    if shifted:
        text(d,(int(w*.25),second),b//10,font); text(d,(tens,second),b%10,font)
    else:
        text(d,(tens,second),b//10,font); text(d,(ones,second),b%10,font)
    if mark and sign=="+":
        text(d,(tens+int(w*.10),bar-int(h*.065)),1,int(h*.145),RED)
    elif mark and sign=="−":
        cy=int(h*.088)
        r=max(3,int(h*.018))
        d.ellipse((tens-r,cy-r,tens+r,cy+r),fill=RED)
    d.line((int(w*.13),bar,int(w*.88),bar),fill=INK,width=max(3,w//75))
    if answer is not None:
        if answer >= 10: text(d,(tens,answer_y),answer//10,font)
        text(d,(ones,answer_y),answer%10,font)
    return im


def badge(sign, exchange):
    im,d=panel((224,224))
    text(d,(111,63),sign,98)
    if exchange:
        stroke(d,55,120,8,tens=True)
        for i in range(10):stroke(d,118+i%5*15,137+i//5*20,10)
        d.line((80,153,106,153),fill=RED,width=4)
        if sign=="+": d.polygon(((79,153),(91,145),(91,161)),fill=RED)
        else: d.polygon(((108,153),(96,145),(96,161)),fill=RED)
    else:
        for i in range(4):stroke(d,70+i*24,151,15)
    return im


def compose(images, size=(900, 580), *, columns=2):
    im,_=panel(size)
    w,h=size
    rows=(len(images)+columns-1)//columns
    cw,ch=(w-30)//columns,(h-25)//rows
    for i,picture in enumerate(images):
        fitted=ImageOps.contain(picture,(cw-12,ch-12),Image.Resampling.LANCZOS)
        im.alpha_composite(fitted,(15+i%columns*cw+(cw-fitted.width)//2,12+i//columns*ch+(ch-fitted.height)//2))
    return im


def model(tens, ones, *, crossed=(0,0), result=None):
    im,d=panel()
    stock(d,(18,38,525,255),tens,ones,crossed=crossed)
    if result is not None:
        text(d,(279,296),result,40)
    return im


def number_pair(a,sign,b):
    im,d=panel((650,355))
    text(d,(325,48),f"{a} {sign} {b}",56)
    stock(d,(16,98,287,212),*divmod(a,10))
    text(d,(325,200),sign,36)
    stock(d,(355,98,276,212),*divmod(b,10))
    return im


def removal_story(total, carried_away):
    im, d = panel((650, 355))
    d.rounded_rectangle((16, 87, 300, 322), radius=18, outline=LINE, width=3)
    d.rounded_rectangle((350, 87, 634, 322), radius=18, outline=LINE, width=3)
    stock(d, (22, 103, 271, 200), *divmod(total, 10))
    stock(d, (356, 103, 271, 200), *divmod(carried_away, 10))
    text(d, (158, 55), total, 54)
    text(d, (492, 55), carried_away, 54)
    d.line((302, 207, 341, 207), fill=GREEN, width=6)
    d.polygon(((346, 207), (331, 194), (331, 220)), fill=GREEN)
    return im


def exchange_record(a,sign,b):
    x,y=divmod(a,10)
    tens_b,ones_b=divmod(b,10)
    n=computed(a,sign,b)
    if sign=="+":
        models=[model(x+tens_b,y+ones_b),model(x+tens_b+1,y+ones_b-10)]
    else:
        models=[model(x,y),model(x-1,y+10)]
    return compose([compose(models,(560,580),columns=1),column_card(a,sign,b,answer=n,mark=True)],(920,590))


def result_badge(n):
    im,d=panel((224,224))
    text(d,(112,106),n,118)
    return im


def matte(im):
    im=im.convert("RGBA")
    data=im.load()
    for y in range(im.height):
        for x in range(im.width):
            r,g,b,a=data[x,y]
            if r>148 and g>193 and b>168 and g-r>13 and b-r>3:
                data[x,y]=(r,g,b,0)
    return im.crop(im.getbbox())


def usage():
    path=ROOT/"lesson.json"
    if not path.is_file():
        return {}
    uses={}
    def add(asset,at):uses.setdefault(asset,set()).add(at)
    for scene in json.loads(path.read_text())["scenes"]:
        key=scene["key"]
        if scene["type"]=="slide":
            for field in ("picture", "left_picture", "right_picture"):
                if field in scene["data"]:
                    add(scene["data"][field],key)
        elif scene["type"]=="interactive":
            add(scene["startImage"],key)
            for ext in (".js",".html"):
                for asset in re.findall(r"__IMG:([a-z0-9-]+)__",(ROOT/"pages"/(scene["page"]+ext)).read_text()):
                    add(asset,key)
        else:
            for q in scene["questions"]:
                add(q["visual"]["image"],f"{key}/{q['id']}/stem")
                for k, option in q["options"].items():add(option["visual"]["image"],f"{key}/{q['id']}/{k}")
    return uses


def render():
    art=Image.open(ATLAS).convert("RGBA")
    assert art.size==(1254,1254)
    illustr={
        "cover":art.crop((2,2,624,624)),
        "sort-backdrop":ImageOps.fit(art.crop((632,4,1250,622)),(960,540),centering=(.5,.19)),
        "repair-backdrop":ImageOps.fit(art.crop((2,632,622,1250)),(960,540),centering=(.5,.22)),
        "trolley":matte(art.crop((645,669,935,921))),
        "leaf-badge":matte(art.crop((653,940,920,1228))),
        "record-badge":matte(art.crop((944,657,1228,923))),
    }
    examples=[(24,"+",43),(28,"+",46),(76,"−",32),(72,"−",48)]
    records={
        "alignment-add":compose([number_pair(24,"+",43),column_card(24,"+",43,answer=67)],(1000,355)),
        "alignment-sub":compose([number_pair(76,"−",32),column_card(76,"−",32,answer=44)],(1000,355)),
        "carry-board":exchange_record(28,"+",46),
        "carry-exact-ten":compose([model(6,10),model(7,0),column_card(46,"+",24,answer=70,mark=True)],(900,385),columns=3),
        "borrow-board":exchange_record(72,"−",48),
        "four-rules":compose([column_card(a,sign,b,answer=computed(a,sign,b),mark=needs_mark(a,sign,b)) for a,sign,b in examples]),
        "copy-check-board":compose([column_card(67,"−",32,answer=35),column_card(67,"−",23,answer=44)],(775,350)),
        "change-check-board":compose([column_card(27,"+",46,answer=63),column_card(27,"+",46,answer=73,mark=True),
            column_card(83,"−",57,answer=36,mark=True),column_card(83,"−",57,answer=26,mark=True)]),
        "use-merge":number_pair(35,"+",22),
        "use-remove":number_pair(69,"−",38),
        "sort-add":compose([badge("+",False),badge("+",True)],(400,185)),
        "sort-sub":compose([badge("−",False),badge("−",True)],(400,185)),
        "sort-mix":compose([badge("+",False),badge("+",True),badge("−",False),badge("−",True)],(400,305)),
        "dock-add-keep":badge("+",False),"dock-add-carry":badge("+",True),
        "dock-sub-keep":badge("−",False),"dock-sub-borrow":badge("−",True),
        **{key:column_card(*args,tiny=True) for key,args in SORT.items()},
        **{f"repair-{key}":column_card(*args) for key,args in REPAIR.items()},
        **{f"tile-{key}":column_card(*args,tiny=True) for key,args in REPAIR.items()},
        "tile-copy-plus-correct":column_card(43,"+",15,answer=58,tiny=True),
        "tile-copy-plus-swapped":column_card(43,"+",51,answer=94,tiny=True),
        "tile-copy-minus-correct":column_card(64,"−",31,answer=33,tiny=True),
        **{f"result-{n}":result_badge(n) for n in RESULT_TARGETS},
    }
    questions = [
        (number_pair(45,"+",23),[column_card(45,"+",23,shifted=True),column_card(45,"+",23),column_card(45,"+",32)]),
        (number_pair(37,"+",46),[model(7,3),model(7,13),model(8,3)]),
        (number_pair(86,"−",43),[model(8,6,crossed=(4,3)),model(7,16,crossed=(4,3)),model(8,6,crossed=(3,4))]),
        (number_pair(73,"−",56),[model(7,13),model(6,13),model(6,3)]),
        (number_pair(92,"−",85),[column_card(92,"−",85,answer=17,mark=True),column_card(92,"−",58,answer=34,mark=True),column_card(92,"−",85,answer=7,mark=True)]),
        (removal_story(58,24),[compose([column_card(58,"−",24,answer=34),model(3,4)],(850,392)),
            compose([column_card(58,"+",24,answer=82,mark=True),model(8,2)],(850,392)),
            compose([column_card(58,"−",42,answer=16),model(1,6)],(850,392))]),
    ]
    for i,(stem,options) in enumerate(questions,1):
        records[f"q{i}-stem"]=stem
        for letter,picture in zip("abc",options):records[f"q{i}-{letter}"]=picture
    used=usage()
    all_pictures={**illustr,**records}
    if used:
        assert set(used)==set(all_pictures),(set(used)-set(all_pictures),set(all_pictures)-set(used))
    index={}
    for key,picture in all_pictures.items():
        filename=f"{key}.png"
        path=ASSETS/filename
        encoded = BytesIO()
        picture.save(encoded,format="PNG",optimize=True)
        png = encoded.getvalue()
        if not path.is_file() or path.read_bytes() != png:
            path.write_bytes(png)
        index[key]={"path":f"assets/{filename}","sha256":sha256(png).hexdigest(),
                    "width":picture.width,"height":picture.height,
                    "source":"observation-station" if key in illustr else "diagrams.py",
                    "uses":sorted(used.get(key,()))}
    record={"schemaVersion":"mira.courseware.asset-sources.v1","generatedBy":"codex_builtin_imagegen",
            "imagegenPlan":"imagegen-plan.json",
            "diagramProgram":{"path":"diagrams.py","sha256":sha256(Path(__file__).read_bytes()).hexdigest()},
            "plates":{"observation-station":{"source":str(ATLAS.relative_to(ROOT)),
                       "sourceSha256":sha256(ATLAS.read_bytes()).hexdigest(),"width":art.width,"height":art.height}},
            "assets":index}
    (ROOT/"asset-sources.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    render()

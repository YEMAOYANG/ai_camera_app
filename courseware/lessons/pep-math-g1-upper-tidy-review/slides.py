"""Slide re-layout for the 7 explanation pages + a replica renderer to check overlaps.
Canvas is 1000 x 562.5.  Only left/top/width/height (and a few font sizes / texts) change; element ids are kept so the
teacher's spotlight actions still land on the same elements."""
import html as _html, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MEDIA = "file:///Users/sqcopenclaw/Desktop/ai_camera_app/openmaic-runtime/.runtime/OpenMAIC/data/classrooms/stage-r8nFZsLo9P/media/"

# slide index -> {id prefix: (left, top, width, height)}; None = delete the element
LAYOUT = {
    2: {
        "text_EEeKBHV": (60, 22, 880, 70), "shape_LvLxac": (190, 94, 620, 4),
        "image___Rd33": (60, 112, 400, 225), "line_TAGp8Ic": None,
        "shape__xT79q": (60, 352, 400, 100), "text_cpfAuck": (70, 362, 380, 80),
        # four speakers, one row each
        "shape_Ag5WXC": (520, 112, 84, 84), "text_q0wlhy8": (530, 134, 64, 42), "shape_tUBw8g": (620, 112, 320, 84), "text_Go1oLkw": (632, 126, 296, 48),
        "shape_QNWEuT": (520, 216, 84, 84), "text_aPN7fmF": (530, 238, 64, 42), "shape_kQtu6N": (620, 216, 320, 84), "text_Msh8L5f": (632, 230, 296, 48),
        "shape_E1JbQg": (520, 320, 84, 84), "text_28xhoKA": (530, 342, 64, 42), "shape_OnasRu": (620, 320, 320, 84), "text_CfaIbWm": (632, 334, 296, 48),
        "shape_H0ssvy": (520, 424, 84, 84), "text_3tH3JHJ": (530, 446, 64, 42), "shape_ioDEEa": (620, 424, 320, 84), "text__wmjBcE": (632, 438, 296, 48),
    },
    3: {
        "text_InhZfl": (60, 20, 880, 64),
        "image_TO2VL": (60, 96, 380, 213), "shape_K9BqN94y": (50, 88, 400, 229),
        "shape_KfO-AWsr": None, "shape_GfY3cmto": None,
        "shape_EFXq2j1D": (470, 96, 70, 84), "text_TXBv54QK": (480, 107, 50, 62),
        "shape_jNIp": (552, 96, 70, 84), "text_xDhAo": (562, 107, 50, 62),
        "shape_z5Wo": (634, 96, 70, 84), "text_5VwyB": (644, 107, 50, 62),
        "shape_1ddz": (716, 96, 70, 84), "text_jy5Nc": (726, 107, 50, 62),
        "shape_6bvC": (798, 96, 70, 84), "text_iuG3f": (808, 107, 50, 62),
        "shape_5XiT": (880, 96, 70, 84), "text_3xqO6": (890, 107, 50, 62),
        "text_P545c7d1": (60, 322, 380, 42),
        "text_muNkA9Dd": (470, 200, 230, 50), "text_vqy6dqDP": (710, 200, 230, 50),
        "shape_8jG9j8A9": (60, 372, 880, 108), "text_9KZBtmsp": (80, 380, 840, 92),
        "text_bBVgVbEA": (60, 490, 880, 50),
    },
    7: {
        "text_GkY8L": (60, 20, 880, 70),
        "image_PC-t": (60, 104, 420, 236),
        "text_JunEmuG-": (510, 112, 430, 53), "text_mldkddT1": (510, 170, 430, 53), "text_mJJFa958": (510, 228, 430, 53),
        "shape_1em65vsg": (60, 372, 280, 120), "text_uYTyvGD6": (60, 380, 280, 104),
        "shape_Zhfe6A4C": (360, 372, 280, 120), "text_hZSsG1VD": (360, 380, 280, 104),
        "shape_bddVIPVf": (660, 372, 280, 120), "text_VSpRociC": (660, 380, 280, 104),
    },
    15: {
        "text_U7irf55": (60, 24, 880, 76), "text_2Xb954l": (60, 100, 880, 43), "shape_PDkAEx": None,
        # decorative lines: one of them ran through the "21张卡" oval in the real player
        "line_F9Fzewf": None, "line_dpb6NHi": None, "line_YW2tBXH": None, "line_WKRj3p1": None, "line_2HxX0Si": None,
        "image_4wJ8OW": (210, 156, 580, 326), "shape_1gNZB84P": (180, 146, 640, 346),
        "shape_MTu4Gpr": (835, 425, 130, 80), "shape_36swrmJZ": (837, 427, 126, 76), "text_lVaoMjV3": (857, 444, 86, 43),
    },
}
FONT = {  # id prefix -> (old font-size px, new font-size px)
    3: {"text_TXBv54QK": (20, 28), "text_xDhAo": (20, 28), "text_5VwyB": (20, 28), "text_jy5Nc": (20, 28), "text_iuG3f": (20, 28), "text_3xqO6": (20, 28),
        "text_9KZBtmsp": (18, 22), "text_bBVgVbEA": (16, 18), "text_muNkA9Dd": (16, 18), "text_vqy6dqDP": (16, 18)},
    7: {"text_JunEmuG-": (18, 22), "text_mldkddT1": (16, 22), "text_mJJFa958": (16, 22)},
}
# slide 7: the second rhyme line was wrong ("同样多用大于号"); fixed here and in the teacher's audio.
FIX_TEXT = {7: {"text_mJJFa958": ("同样多用大于号，同样少用小于号。", "一样多用等于号，大口朝着多的那边。")}}
LINE_FIX = ("同样多用大于号，同样少用小于号。", "一样多用等于号，大口朝着多的那边。")


def pick(scene, prefix):
    m = [e for e in scene["content"]["canvas"]["elements"] if e["id"].startswith(prefix)]
    if len(m) != 1:
        raise KeyError("%s matches %d elements" % (prefix, len(m)))
    return m[0]


def relayout(scenes):
    for idx, rules in LAYOUT.items():
        sc = scenes[idx - 1]
        els = sc["content"]["canvas"]["elements"]
        for prefix, geo in rules.items():
            e = pick(sc, prefix)
            if geo is None:
                els.remove(e)
            else:
                e["left"], e["top"], e["width"], e["height"] = geo
        for prefix, (old, new) in FONT.get(idx, {}).items():
            e = pick(sc, prefix)
            c = e["content"]
            c2 = re.sub(r"font-size:\s*%dpx" % old, "font-size: %dpx" % new, c)
            assert c2 != c, (idx, prefix)
            e["content"] = c2
        for prefix, (old, new) in FIX_TEXT.get(idx, {}).items():
            e = pick(sc, prefix)
            assert old in e["content"], (idx, prefix)
            e["content"] = e["content"].replace(old, new)
    # the slide-7 teacher line
    sp = [a for a in scenes[6]["actions"] if a["type"] == "speech" and a["text"] == LINE_FIX[0]]
    assert len(sp) == 1
    return sp[0]


def replica_page(scene):
    cv = scene["content"]["canvas"]
    parts = []
    for e in cv["elements"]:
        st = "position:absolute;left:%spx;top:%spx;width:%spx;height:%spx;" % (e["left"], e["top"], e["width"], e.get("height", 0))
        i = _html.escape(e["id"])
        if e["type"] == "text":
            parts.append('<div class="t" data-id="%s" style="%s"><div class="c" style="color:%s">%s</div></div>' % (i, st, e.get("defaultColor", "#333"), e["content"]))
        elif e["type"] == "image":
            parts.append('<img class="im" data-id="%s" style="%sobject-fit:fill" src="%s">' % (i, st, e["src"].replace("/api/classroom-media/stage-r8nFZsLo9P/media/", MEDIA)))
        elif e["type"] == "shape":
            fill = e.get("fill", "transparent")
            parts.append('<div class="sh" data-id="%s" data-fill="%s" style="%sbackground:%s"></div>' % (i, fill, st, fill if fill != "transparent" else "transparent"))
        elif e["type"] == "latex":
            parts.append('<div class="lx" data-id="%s" style="%s"></div>' % (i, st))
        else:
            parts.append('<div class="ot" data-id="%s" data-type="%s" style="%s"></div>' % (i, e["type"], st))
    js = r"""
var out=[];document.querySelectorAll('[data-id]').forEach(function(n){var r=n.getBoundingClientRect(),box=n.className,real=r;
 if(n.classList.contains('t')){var c=n.querySelector('.c');var cr=c.getBoundingClientRect();real={left:cr.left,top:cr.top,right:cr.right,bottom:cr.bottom}}
 out.push({id:n.dataset.id,k:n.className,fill:n.dataset.fill||'',box:[r.left,r.top,r.right,r.bottom],real:[real.left,real.top,real.right,real.bottom],text:(n.textContent||'').trim().slice(0,12)})});
document.getElementById('res').textContent=JSON.stringify(out);document.title='DONE';"""
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"><style>*{box-sizing:border-box;margin:0;padding:0}body{background:#fff;font-family:"PingFang SC","Microsoft YaHei",sans-serif}'
            '#cv{position:relative;width:1000px;height:562.5px;overflow:visible;outline:1px solid red}.t .c{padding:10px;line-height:1.5;word-break:break-word}.t .c p+p{margin-top:5px}'
            '.t .c p{margin:0}.im{display:block}</style></head><body><div id="cv">' + "".join(parts) + '</div><pre id="res" style="position:fixed;opacity:0"></pre><script>' + js + '</script></body></html>')


def check(scene, label):
    pg = replica_page(scene)
    path = os.path.join(HERE, "work", "slide_%s.html" % label)
    open(path, "w", encoding="utf-8").write(pg)
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files", "--window-size=1000,640",
                        "--virtual-time-budget=4000", "--dump-dom", "file://" + path], capture_output=True, text=True, timeout=60)
    m = re.search(r'<pre id="res"[^>]*>(.*?)</pre>', r.stdout, re.S)
    rows = json.loads(_html.unescape(m.group(1)))
    probs = []
    texts = [x for x in rows if x["k"] == "t"]
    ims = [x for x in rows if x["k"] == "im"]
    shapes = [x for x in rows if x["k"] == "sh" and x["fill"] not in ("transparent", "")]

    def ink(x):  # text ink area: real rect minus the 10px padding
        l, t, rr, b = x["real"]
        return (l + 10, t + 10, rr - 10, b - 10)

    def inter(a, b):
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        return (w, h) if w > 1 and h > 1 else None

    for x in rows:
        if x["k"] in ("sh",) and x["fill"] in ("transparent", ""):
            continue
        b = x["real"] if x["k"] == "t" else x["box"]
        if b[0] < -1 or b[1] < -1 or b[2] > 1001 or b[3] > 563.5:
            probs.append("%s 出画面 %s %s" % (label, x["id"][:14], [round(v) for v in b]))
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            ov = inter(ink(a), ink(b))
            if ov:
                probs.append("%s 文字重叠 %s %s / %s %s (%dx%d)" % (label, a["id"][:12], a["text"], b["id"][:12], b["text"], ov[0], ov[1]))
        for im in ims:
            ov = inter(ink(a), im["box"])
            if ov:
                probs.append("%s 文字压图 %s %s / %s" % (label, a["id"][:12], a["text"], im["id"][:12]))
        cont = [s for s in shapes if s["box"][0] - 2 <= ink(a)[0] <= s["box"][2] and s["box"][1] - 2 <= ink(a)[1] <= s["box"][3]]
        if cont:
            s = min(cont, key=lambda q: (q["box"][2] - q["box"][0]) * (q["box"][3] - q["box"][1]))
            ia = ink(a)
            if ia[2] > s["box"][2] + 2 or ia[3] > s["box"][3] + 2:
                probs.append("%s 文字超出卡片 %s %s 底%d>卡%d" % (label, a["id"][:12], a["text"], ia[3], s["box"][3]))
    for i, a in enumerate(ims):
        for b in ims[i + 1:]:
            if inter(a["box"], b["box"]):
                probs.append("%s 图压图 %s / %s" % (label, a["id"][:12], b["id"][:12]))
    return probs, rows

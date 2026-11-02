import importlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


MEDIA_DIR = "/Users/sqcopenclaw/Desktop/ai_camera_app/openmaic-runtime/.runtime/OpenMAIC/data/classrooms/stage-r8nFZsLo9P/media/"
FULL = {f[10:18]: f for f in os.listdir(MEDIA_DIR) if f.startswith("generated-")}
OWL, BASKET, DISCS, TEAM, PREVIEW = "9c545b5f", "43fd07a0", "6add1591", "ad24c5ac", "4f5d4009"
IMG = {"p04": BASKET, "p05": OWL, "p08": OWL, "p09": TEAM, "p10": TEAM, "p13": DISCS, "p16": TEAM, "p17": TEAM, "p18": TEAM,
       "p19": TEAM, "p20": TEAM, "p21": TEAM, "p22": TEAM, "p23": TEAM, "p25": OWL, "p26": PREVIEW}


def collect():
    pages = {}
    for m in ("pages_a", "pages_b", "pages_c", "pages_d", "pages_e"):
        try:
            mod = importlib.import_module(m)
        except ModuleNotFoundError:
            continue
        pages.update(mod.PAGES)
    return pages


if __name__ == "__main__":
    os.makedirs(HERE + "/out", exist_ok=True)
    want = sys.argv[1:]
    for name, fn in sorted(collect().items()):
        if want and name not in want:
            continue
        html = fn()
        html = html.replace('__IMG__', FULL[PREVIEW])
        pre = IMG.get(name)
        if pre and "K.ready({" in html:
            html = html.replace("K.ready({", "K.ready({img:'" + FULL[pre] + "',", 1)
        open(f"{HERE}/out/{name}.html", "w", encoding="utf-8").write(html)
        print(name, len(html.encode("utf-8")), "bytes")

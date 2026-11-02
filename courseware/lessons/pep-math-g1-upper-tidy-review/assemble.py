"""Assemble the final classroom: new interactive pages + re-laid-out slides + corrected teacher lines (re-voiced).
Writes final/body.json (the POST body) and copies the media into the new classroom folder."""
import base64, hashlib, json, os, random, re, shutil, string, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build, slides  # noqa: E402

SP = os.path.dirname(HERE)
ROOT = "/Users/sqcopenclaw/Desktop/ai_camera_app/openmaic-runtime/.runtime/OpenMAIC/data/classrooms/"
OLD = "stage-r8nFZsLo9P"
MAP = {4: "p04", 5: "p05", 8: "p08", 9: "p09", 10: "p10", 13: "p13", 16: "p16", 17: "p17", 18: "p18", 19: "p19", 20: "p20", 21: "p21",
       22: "p22", 23: "p23", 25: "p25", 26: "p26"}
# Teacher lines that were wrong or described a control that no longer exists. scene -> [(action id, new text, [extra lines inserted after it])]
FIXES = {
    7: [("action_E_vVjyLr", "一样多用等于号，大口朝着多的那边。", [])],
    8: [("action_MR_B26Vj", "大于号的口朝左边，小于号的口朝右边。", ["3比4少，所以3小于4。", "我先试着选小于号。"]),
        ("action_T-Kjl7_g", "现在轮到你啦，先数一数两边，再选一个符号。", [])],
}
PREV = "stage-ErDm4dzaFm"  # version already saved (and archived): a registered id can never be overwritten, so every re-save needs a new id
os.makedirs(HERE + "/final", exist_ok=True)
idfile = HERE + "/final/new-id.txt"
NEW = open(idfile).read().strip() if os.path.exists(idfile) else PREV
if NEW == PREV:
    NEW = "stage-" + "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(10))
    open(idfile, "w").write(NEW)
cachefile = HERE + "/final/tts-cache.json"
cache = json.load(open(cachefile)) if os.path.exists(cachefile) else {}

raw = json.load(open(SP + "/pilot2/readback.json", encoding="utf-8"))
d = raw["data"]["classroom"] if "data" in raw else raw["classroom"]
scenes = d["scenes"]


def strip_tests(h):
    """Remove the test helpers and each page's __test routine from the shipped HTML."""
    h = re.sub(r"/\*T\*/.*?/\*E\*/", "", h, flags=re.S)
    i = h.rindex("window.__test=")
    j = h.rindex("})();")
    return h[:i] + h[j:]


# 1. pages
built = {n: fn() for n, fn in build.collect().items()}
for idx, name in MAP.items():
    s = scenes[idx - 1]
    assert s["type"] == "interactive", idx
    html = built[name]
    if name in build.IMG and "K.ready({" in html:
        html = html.replace("K.ready({", "K.ready({img:'/api/classroom-media/__STAGE__/media/" + build.FULL[build.IMG[name]] + "',", 1)
    html = html.replace("__IMG__", build.FULL[build.PREVIEW])
    assert not re.search(r"__(IMG|MODE|DEMO|PAGE|TITLE|SUB|SAY)__", html), name
    html = strip_tests(html)
    open(HERE + "/out/" + name + ".final.html", "w", encoding="utf-8").write(html)
    s["content"]["html"] = html

# 2. slides (geometry, rhyme text on slide 7)
slides.relayout(scenes)

# 3. corrected teacher lines: edit the text now, voice them after the id rename
todo = []  # action dicts needing new audio
for idx, fixes in FIXES.items():
    acts = scenes[idx - 1]["actions"]
    for aid, text, extra in fixes:
        pos = [i for i, a in enumerate(acts) if a["id"] == aid]
        assert len(pos) == 1 and acts[pos[0]]["type"] == "speech", (idx, aid)
        acts[pos[0]]["text"] = text
        todo.append(acts[pos[0]])
        for k, t in enumerate(extra, 1):
            na = {"id": "%s_s%d" % (aid, k), "type": "speech", "text": t}
            acts.insert(pos[0] + k, na)
            todo.append(na)

# 4. rename the classroom id everywhere (JSON text), pages get the final id too
text = json.dumps(d, ensure_ascii=False).replace(OLD, NEW).replace("__STAGE__", NEW)
d = json.loads(text)
scenes = d["scenes"]
ids = {a["id"] for a in todo}
todo = [a for s in scenes for a in s["actions"] if a["id"] in ids]
assert len(todo) == len(ids)

# 5. voice them with the same teacher voice as the other clips (reuse an earlier run's clip for the same id+text)
os.makedirs(ROOT + NEW + "/media", mode=0o700, exist_ok=True)
for _key, _f in list(cache.items()):  # clips voiced for the previous save: reuse them, no new TTS call
    if os.path.exists(ROOT + PREV + "/media/" + _f) and not os.path.exists(ROOT + NEW + "/media/" + _f):
        shutil.copyfile(ROOT + PREV + "/media/" + _f, ROOT + NEW + "/media/" + _f)
for a in todo:
    key = a["id"] + "|" + a["text"]
    fname = cache.get(key)
    if fname and os.path.exists(ROOT + NEW + "/media/" + fname):
        wav = open(ROOT + NEW + "/media/" + fname, "rb").read()
    else:
        req = urllib.request.Request("http://127.0.0.1:3100/api/generate/tts", method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"text": a["text"], "audioId": a["id"], "ttsProviderId": "qwen-tts", "ttsModelId": "qwen3-tts-flash",
                                                      "ttsVoice": "Ethan"}).encode())
        resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
        wav = base64.b64decode(resp.get("data", resp)["base64"])
        fname = "tts-%s-%s.wav" % (a["id"], hashlib.sha256(wav).hexdigest())
        open(ROOT + NEW + "/media/" + fname, "wb").write(wav)
        cache[key] = fname
    url = "/api/classroom-media/%s/media/%s" % (NEW, fname)
    a["audioId"] = url
    a["audioUrl"] = url
json.dump(cache, open(cachefile, "w"))

# 6. copy every referenced media file into the new folder (hash-checked against the name); drop stale clips
text = json.dumps(d, ensure_ascii=False)
names = sorted(set(re.findall(r"/api/classroom-media/" + NEW + r"/media/([A-Za-z0-9_.\-]+)", text)))
missing = []
for n in names:
    dst = ROOT + NEW + "/media/" + n
    if os.path.exists(dst):
        continue
    src = ROOT + OLD + "/media/" + n
    if not os.path.exists(src):
        src = ROOT + PREV + "/media/" + n
    if not os.path.exists(src):
        missing.append(n)
        continue
    shutil.copyfile(src, dst)
    os.chmod(dst, 0o600)
extra_files = sorted(set(os.listdir(ROOT + NEW + "/media")) - set(names))
for f in extra_files:
    os.remove(ROOT + NEW + "/media/" + f)
bad = 0
for n in names:
    m = re.search(r"([0-9a-f]{64})\.(png|wav)$", n)
    if m and hashlib.sha256(open(ROOT + NEW + "/media/" + n, "rb").read()).hexdigest() != m.group(1):
        bad += 1
body = json.dumps({"stage": d["stage"], "scenes": d["scenes"]}, ensure_ascii=False)
open(HERE + "/final/body.json", "w", encoding="utf-8").write(body)
sp = [a for s in scenes for a in s["actions"] if a["type"] == "speech"]
print("new id:", NEW, "| media:", len(names), "| missing:", missing, "| removed stale:", len(extra_files), "| hash mismatches:", bad, "| body bytes:", len(body.encode()))
print("speech lines:", len(sp), "| without audio:", sum(1 for a in sp if not a.get("audioUrl")), "| revoiced:", len(todo))

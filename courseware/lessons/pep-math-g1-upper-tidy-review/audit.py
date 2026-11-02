import html, json, os, re, subprocess, sys

SP = "/private/tmp/claude-501/-Users-sqcopenclaw--claude-spares-spare-6WO2cM/69524702-c015-49b7-8662-90207a7d0335/scratchpad/gen"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MEDIA = "file:///Users/sqcopenclaw/Desktop/ai_camera_app/openmaic-runtime/.runtime/OpenMAIC/data/classrooms/stage-r8nFZsLo9P/media/"
os.makedirs(SP + "/work", exist_ok=True)
os.makedirs(SP + "/shots", exist_ok=True)

HARNESS = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>wait</title></head><body style="margin:0;background:#222">
<iframe id="f" style="border:0;display:block;width:%(w)dpx;height:%(h)dpx" srcdoc="%(src)s"></iframe>
<pre id="res" style="position:fixed;left:0;top:0;opacity:0;font-size:1px"></pre>
<script>
var STOP=%(stop)d, RUN=%(run)s, SELS=%(sels)s;
var f=document.getElementById('f');
f.addEventListener('load',async function(){
  var out={errs:[],problems:[],test:null,cps:[]};
  try{
    var w=f.contentWindow; await new Promise(function(r){setTimeout(r,500)});
    if(w.K){w.K.stopAt=STOP; if(w.K.audit)w.K.audit('初始');}
    if(RUN&&w.__test){out.test=await w.__test();}
    out.missing=SELS.filter(function(s){return !w.document.querySelector(s)});
    if(w.K){if(w.K.audit)w.K.audit('结束'); out.problems=w.K.problems||[]; out.errs=w.K.errs; out.cps=w.K.cps||[];}
  }catch(e){out.errs.push('harness:'+e)}
  document.getElementById('res').textContent=JSON.stringify(out); document.title='DONE';
});
</script></body></html>"""


def build_harness(name, w, h, stop=0, run=True, sels=()):
    src = open(f"{SP}/out/{name}.html", encoding="utf-8").read()
    src = src.replace("/api/classroom-media/__STAGE__/media/", MEDIA)
    page = HARNESS % dict(w=w, h=h, src=html.escape(src, quote=True), stop=stop, run="true" if run else "false", sels=json.dumps(list(sels)))
    path = f"{SP}/work/{name}_{w}x{h}_{stop}.html"
    open(path, "w", encoding="utf-8").write(page)
    return path


def chrome(args, timeout=90):
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--allow-file-access-from-files",
           "--autoplay-policy=no-user-gesture-required"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def audit(name, w=1280, h=720, budget=40000, sels=(), run=True):
    path = build_harness(name, w, h, sels=sels, run=run)
    r = chrome([f"--window-size={w},{h}", f"--virtual-time-budget={budget}", "--dump-dom", "file://" + path])
    m = re.search(r'<pre id="res"[^>]*>(.*?)</pre>', r.stdout, re.S)
    if not m:
        return {"fatal": "no result", "stderr": r.stderr[-400:]}
    return json.loads(html.unescape(m.group(1)))


def shot(name, stop, w=1280, h=720, budget=40000):
    path = build_harness(name, w, h, stop=stop, run=stop > 0)
    out = f"{SP}/shots/{name}_{w}_{stop}.png"
    chrome([f"--window-size={w},{h}", f"--virtual-time-budget={budget}", f"--screenshot={out}", "file://" + path])
    return out


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "shot":
        print(shot(sys.argv[2], int(sys.argv[3]), *(int(x) for x in sys.argv[4:6])) if len(sys.argv) > 5 else shot(sys.argv[2], int(sys.argv[3])))
    else:
        names = sys.argv[2:]
        sizes = [(1280, 720)] if mode == "audit" else [(1280, 720), (1000, 563), (640, 360)]
        for n in names:
            for (w, h) in sizes:
                res = audit(n, w, h)
                tests = res.get("test")
                bad = [t for t in (tests or []) if not t[1]] if isinstance(tests, list) else tests
                print(f"== {n} {w}x{h}: errs={res.get('errs')} problems={len(res.get('problems', []))} failedTests={bad if bad else 'none'} cps={len(res.get('cps', []))}")
                for p in res.get("problems", [])[:14]:
                    print("   -", p)
                if res.get("fatal"):
                    print("   FATAL", res)


SANDBOX = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>wait</title></head><body style="margin:0;background:#222">
<iframe id="f" sandbox="allow-scripts allow-forms allow-popups" style="border:0;display:block;width:%(w)dpx;height:%(h)dpx" srcdoc="%(src)s"></iframe>
<pre id="res" style="position:fixed;left:0;top:0;opacity:0;font-size:1px"></pre>
<script>
var f=document.getElementById('f');
setTimeout(function(){f.contentWindow.postMessage('RUN-TEST','*')},1000);
window.addEventListener('message',function(e){var d=e.data;if(d&&d.type==='TEST_RESULT'){document.getElementById('res').textContent=JSON.stringify(d);document.title='DONE'}});
</script></body></html>"""

RUNNER = """<script>window.addEventListener('message',async function(e){if(e.data==='RUN-TEST'){var out={type:'TEST_RESULT',test:null,problems:[],errs:[]};
try{K.audit('初始');out.test=await window.__test();K.audit('结束');out.problems=K.problems;out.errs=K.errs}catch(x){out.errs.push('runner:'+x)}
parent.postMessage(out,'*')}});</script>"""


def sandbox_audit(name, w=1280, h=720, budget=60000):
    src = open(f"{SP}/out/{name}.html", encoding="utf-8").read().replace("/api/classroom-media/__STAGE__/media/", MEDIA)
    src = src.replace("</body>", RUNNER + "</body>")
    path = f"{SP}/work/{name}_sandbox.html"
    open(path, "w", encoding="utf-8").write(SANDBOX % dict(w=w, h=h, src=html.escape(src, quote=True)))
    r = chrome([f"--window-size={w},{h}", f"--virtual-time-budget={budget}", "--dump-dom", "file://" + path])
    m = re.search(r'<pre id="res"[^>]*>(.*?)</pre>', r.stdout, re.S)
    if not m or not m.group(1).strip():
        return {"fatal": "no result from sandboxed page", "stderr": r.stderr[-300:]}
    return json.loads(html.unescape(m.group(1)))

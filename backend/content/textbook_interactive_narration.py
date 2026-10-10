"""Finite, prerecorded teacher cues for private interactive courseware."""
from html.parser import HTMLParser
import json
import re

CUE_SCHEMA = "mira.interactive.narration-cues.v1"
CUE_SCRIPT = "mira-narration-cues"
AUDIO_SCRIPT = "mira-pre-recorded-audio"
IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
AUDIO_BLOCK = re.compile(r'<script id="mira-pre-recorded-audio">[\s\S]*?</script>')
AUDIO_CODE = """(()=>{
const clips=MAP;let active=null;
let generation=0,visible=false;
const state=(cueId,status)=>{document.documentElement.dataset.miraAudioState=status;
window.dispatchEvent(new CustomEvent('mira-narration-state',{detail:{cueId,status}}));};
const stop=(status)=>{generation++;const previous=active;active=null;
if(previous){previous.onended=null;previous.onerror=null;previous.pause();previous.currentTime=0;}
state(null,status);};
window.addEventListener('message',(event)=>{if(event.source!==parent||event.data?.type!=='MIRA_NARRATION_VISIBILITY')return;
visible=event.data.visible===true;if(!visible)stop('hidden');});
window.miraNarrate=async(cueId)=>{stop('ready');const ticket=generation;
if(!visible){state(cueId,'hidden');return false;}
if(!Object.prototype.hasOwnProperty.call(clips,cueId)){state(cueId,'missing');return false;}
const clip=new Audio(clips[cueId]);active=clip;const current=()=>generation===ticket&&active===clip;
clip.onended=()=>{if(current()){active=null;state(cueId,'ready');}};
clip.onerror=()=>{if(current()){active=null;state(cueId,'error');}};
try{await clip.play();if(!current()){clip.pause();return false;}state(cueId,'playing');return true;}
catch(_){if(current()){active=null;state(cueId,'error');}return false;}};
state(null,'ready');})();"""


def _helper(urls):
    return '<script id="mira-pre-recorded-audio">' + AUDIO_CODE.replace(
        "MAP", json.dumps(urls, ensure_ascii=True, separators=(",", ":"))) + "</script>"


class _Cues(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("id") == CUE_SCRIPT:
            if self.active or values.get("type") != "application/json":
                raise ValueError("interactive_narration_script_invalid")
            self.active = True
            self.blocks.append("")

    def handle_data(self, data):
        if self.active:
            self.blocks[-1] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False


def interactive_cues(html):
    if not isinstance(html, str):
        raise ValueError("interactive_html_invalid")
    if re.search(r"speechSynthesis|SpeechSynthesisUtterance", html, re.I):
        raise ValueError("browser_speech_synthesis_forbidden")
    parser = _Cues()
    parser.feed(html)
    if not parser.blocks:
        return []
    if len(parser.blocks) != 1 or parser.active:
        raise ValueError("interactive_narration_script_ambiguous")
    try:
        payload = json.loads(parser.blocks[0])
    except (ValueError, TypeError) as exc:
        raise ValueError("interactive_narration_json_invalid") from exc
    if (not isinstance(payload, dict) or payload.get("schemaVersion") != CUE_SCHEMA
            or not isinstance(payload.get("cues"), list) or not 1 <= len(payload["cues"]) <= 120):
        raise ValueError("interactive_narration_cues_invalid")
    cues, seen = [], set()
    for cue in payload["cues"]:
        if (not isinstance(cue, dict) or IDENTITY.fullmatch(str(cue.get("id", ""))) is None
                or cue["id"] in seen or not isinstance(cue.get("text"), str)
                or not 0 < len(cue["text"].strip()) <= 1000):
            raise ValueError("interactive_narration_cue_invalid")
        seen.add(cue["id"])
        cues.append({"id": cue["id"], "text": cue["text"].strip()})
    return cues


def without_audio_helper(html):
    """Only the exact generated audio block is excluded from teaching hashes."""
    blocks = AUDIO_BLOCK.findall(html)
    if len(blocks) > 1:
        raise ValueError("interactive_audio_helper_ambiguous")
    for block in blocks:
        try:
            start = block.index("const clips=") + len("const clips=")
            end = block.index(";let active=null;", start)
            urls = json.loads(block[start:end])
        except (ValueError, TypeError) as exc:
            raise ValueError("interactive_audio_helper_changed") from exc
        if (not isinstance(urls, dict) or block != _helper(urls)
                or any(IDENTITY.fullmatch(key) is None or not isinstance(url, str)
                       or re.fullmatch(r"/api/classroom-media/[A-Za-z0-9_-]+/audio/[A-Za-z0-9_-]+\.wav", url) is None
                       for key, url in urls.items())):
            raise ValueError("interactive_audio_helper_changed")
    return AUDIO_BLOCK.sub("", html)


def bind_interactive_audio(html, urls, classroom_id):
    cues = interactive_cues(html)
    if set(urls) != {cue["id"] for cue in cues}:
        raise ValueError("interactive_audio_cue_coverage_incomplete")
    prefix = f"/api/classroom-media/{classroom_id}/audio/"
    if not IDENTITY.fullmatch(classroom_id) or any(
            not isinstance(url, str) or not url.startswith(prefix)
            or re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_-]+\.wav", url) is None
            for url in urls.values()):
        raise ValueError("interactive_audio_url_invalid")
    # Only our helper owns this symbol. Generated activities call it; they do
    # not synthesise speech or override the finite, audited sound inventory.
    source = without_audio_helper(html)
    if re.search(r"(?:window\s*\.\s*miraNarrate\s*=|function\s+miraNarrate\b)", source):
        raise ValueError("interactive_audio_player_override_forbidden")
    helper = _helper(urls)
    opening = re.search(r"<head(?:\s[^>]*)?>", source, re.I)
    if opening:
        return source[:opening.end()] + helper + source[opening.end():]
    return helper + source

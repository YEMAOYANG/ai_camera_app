import json
import shutil
import subprocess
import unittest

from content.textbook_interactive_narration import (bind_interactive_audio, interactive_cues,
                                                   without_audio_helper)


def activity(cues=None):
    payload = {"schemaVersion": "mira.interactive.narration-cues.v1", "cues": cues or [
        {"id": "find-cat", "text": "请看小猫。"}, {"id": "try-again", "text": "再看一看。"}]}
    return ('<!doctype html><html><head></head><body><script type="application/json" '
            'id="mira-narration-cues">' + json.dumps(payload, ensure_ascii=False) + '</script>'
            '<button onclick="window.miraNarrate(\'find-cat\')">重听</button></body></html>')


class InteractiveNarrationTest(unittest.TestCase):
    def test_finite_inventory_and_safe_complete_audio_binding(self):
        html = activity()
        self.assertEqual([cue["id"] for cue in interactive_cues(html)], ["find-cat", "try-again"])
        urls = {cue["id"]: f"/api/classroom-media/room-1/audio/{cue['id']}.wav"
                for cue in interactive_cues(html)}
        bound = bind_interactive_audio(html, urls, "room-1")
        self.assertEqual(without_audio_helper(bound), html)
        self.assertEqual(bind_interactive_audio(bound, urls, "room-1"), bound)
        self.assertIn("new Audio(clips[cueId])", bound)
        self.assertNotIn("speechSynthesis", bound)
        with self.assertRaisesRegex(ValueError, "helper_changed"):
            without_audio_helper(bound.replace("new Audio(clips[cueId])", "new Audio('elsewhere')"))

    @unittest.skipUnless(shutil.which("node"), "Node is required for the asynchronous audio behaviour check")
    def test_late_audio_callbacks_and_hidden_iframe_cannot_overwrite_active_playback(self):
        bound = bind_interactive_audio(activity(), {"find-cat": "/api/classroom-media/room-1/audio/a.wav",
                                                   "try-again": "/api/classroom-media/room-1/audio/b.wav"}, "room-1")
        code = bound.split('<script id="mira-pre-recorded-audio">', 1)[1].split("</script>", 1)[0]
        setup = """
const assert=require('node:assert/strict');const events=[],listeners={},clips=[];
global.parent={};global.document={documentElement:{dataset:{}}};
global.CustomEvent=class{constructor(name,value){this.detail=value.detail;}};
global.window={dispatchEvent:e=>events.push(e.detail),addEventListener:(type,fn)=>listeners[type]=fn};
global.Audio=class{constructor(url){this.url=url;this.paused=false;clips.push(this);}
play(){return new Promise((resolve,reject)=>{this.resolve=resolve;this.reject=reject;});}
pause(){this.paused=true;}};
"""
        checks = """
(async()=>{
assert.equal(await window.miraNarrate('find-cat'),false);assert.equal(clips.length,0);
listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:true}});
const a=window.miraNarrate('find-cat'),first=clips[0],oldEnded=first.onended;
const b=window.miraNarrate('try-again'),second=clips[1];second.resolve();await b;
assert.deepEqual(events.at(-1),{cueId:'try-again',status:'playing'});
first.resolve();await a;oldEnded();assert.deepEqual(events.at(-1),{cueId:'try-again',status:'playing'});
listeners.message({source:{},data:{type:'MIRA_NARRATION_VISIBILITY',visible:false}});
assert.equal(second.paused,false);
listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:false}});
assert.equal(second.paused,true);assert.equal(events.at(-1).status,'hidden');
assert.equal(await window.miraNarrate('find-cat'),false);assert.equal(clips.length,2);
listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:true}});
const c=window.miraNarrate('find-cat');clips[2].resolve();await c;clips[2].onended();
assert.deepEqual(events.at(-1),{cueId:'find-cat',status:'ready'});
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run([shutil.which("node"), "-e", setup + code + checks], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_extra_or_external_audio_is_rejected(self):
        for urls in ({}, {"unknown": "/api/classroom-media/room-1/audio/x.wav"},
                     {"find-cat": "https://example.org/a.wav", "try-again": "/api/classroom-media/room-1/audio/y.wav"},
                     {"find-cat": "/api/classroom-media/room-2/audio/x.wav", "try-again": "/api/classroom-media/room-1/audio/y.wav"}):
            with self.assertRaises(ValueError):
                bind_interactive_audio(activity(), urls, "room-1")

    def test_browser_speech_and_player_overrides_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "browser_speech"):
            interactive_cues(activity() + '<script>new SpeechSynthesisUtterance("x")</script>')
        urls = {cue["id"]: f"/api/classroom-media/room-1/audio/{cue['id']}.wav" for cue in interactive_cues(activity())}
        with self.assertRaisesRegex(ValueError, "override"):
            bind_interactive_audio(activity() + '<script>window.miraNarrate=()=>{};</script>', urls, "room-1")

    def test_ambiguous_duplicate_invalid_inventory_is_rejected(self):
        invalid = [activity() + activity(), activity([{"id": "same", "text": "一"}, {"id": "same", "text": "二"}]),
                   activity([{ "id": "../escape", "text": "一"}]), activity().replace('application/json', 'text/javascript'),
                   activity().replace('"schemaVersion"', '"wrong"')]
        for html in invalid:
            with self.subTest(html=html[:120]), self.assertRaises(ValueError):
                interactive_cues(html)


if __name__ == "__main__":
    unittest.main()

import json
import shutil
import subprocess
import unittest

from content.textbook_interactive_narration import (_INTERRUPTING_AUDIO_CODE, _QUEUE_AUDIO_CODE, _WAITING_AUDIO_CODE, _helper, bind_interactive_audio,
                                                   interactive_cues, without_audio_helper)


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
const flush=()=>new Promise(resolve=>setTimeout(resolve,0));
const realNow=Date.now;let clock=0;Date.now=()=>realNow()+clock;
assert.equal(await window.miraNarrate('find-cat'),false);assert.equal(clips.length,0);
// A line asked for long before the page may speak is not played late.
clock=5000;listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:true}});
assert.equal(clips.length,0);
const a=window.miraNarrate('find-cat'),first=clips[0];
// A second line waits for the one being spoken instead of cutting it off.
assert.equal(await window.miraNarrate('try-again'),true);assert.equal(clips.length,1);
assert.deepEqual(events.at(-1),{cueId:'try-again',status:'queued'});
first.resolve();assert.equal(await a,true);assert.equal(first.paused,false);
assert.deepEqual(events.at(-1),{cueId:'find-cat',status:'playing'});
first.onended();assert.deepEqual(events.at(-1),{cueId:'find-cat',status:'ready'});
const second=clips[1];assert.equal(second.url,'/api/classroom-media/room-1/audio/b.wav');
second.resolve();await flush();assert.deepEqual(events.at(-1),{cueId:'try-again',status:'playing'});
first.onended();assert.deepEqual(events.at(-1),{cueId:'try-again',status:'playing'});
// Asking for the line that is playing restarts it.
const again=window.miraNarrate('try-again');assert.equal(second.paused,true);
const third=clips[2];third.resolve();assert.equal(await again,true);
listeners.message({source:{},data:{type:'MIRA_NARRATION_VISIBILITY',visible:false}});
assert.equal(third.paused,false);
window.miraNarrate('find-cat');assert.equal(clips.length,3);
listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:false}});
assert.equal(third.paused,true);assert.equal(events.at(-1).status,'hidden');
assert.equal(third.onended,null);assert.equal(clips.length,3);assert.equal(events.at(-1).status,'hidden');
// A line tapped while the lecture speaks plays as soon as the page may speak.
assert.equal(await window.miraNarrate('find-cat'),false);assert.equal(clips.length,3);
clock+=1500;listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:true}});
assert.equal(clips.length,4);assert.equal(clips[3].url,'/api/classroom-media/room-1/audio/a.wav');
clips[3].resolve();await flush();assert.deepEqual(events.at(-1),{cueId:'find-cat',status:'playing'});
clips[3].onended();assert.deepEqual(events.at(-1),{cueId:'find-cat',status:'ready'});
// Task changes stop sound and its queued successor, including a late play()
// completion. Neither callback may make the cancelled cue ready/playing.
const cancelled=window.miraNarrate('find-cat'),fourth=clips[4];
const lateEnded=fourth.onended;
await window.miraNarrate('try-again');
window.miraCancelNarration();assert.equal(fourth.paused,true);
assert.equal(fourth.onended,null);assert.equal(fourth.onerror,null);
fourth.resolve();assert.equal(await cancelled,false);lateEnded();await flush();
assert.equal(clips.length,5);assert.deepEqual(events.at(-1),{cueId:null,status:'ready'});
// A hidden request must not be resurrected after its task was cancelled.
listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:false}});
assert.equal(await window.miraNarrate('try-again'),false);
window.miraCancelNarration();
listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:true}});
assert.equal(clips.length,5);
// It plays once: becoming visible again does not repeat it.
listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:false}});
listeners.message({source:parent,data:{type:'MIRA_NARRATION_VISIBILITY',visible:true}});
assert.equal(clips.length,5);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run([shutil.which("node"), "-e", setup + code + checks], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_lessons_narrated_with_the_earlier_helper_can_be_narrated_again(self):
        urls = {"find-cat": "/api/classroom-media/room-1/audio/a.wav", "try-again": "/api/classroom-media/room-1/audio/b.wav"}
        earlier = activity().replace("<head>", "<head>" + _helper(urls, _INTERRUPTING_AUDIO_CODE), 1)
        queued = activity().replace("<head>", "<head>" + _helper(urls, _QUEUE_AUDIO_CODE), 1)
        waiting = activity().replace("<head>", "<head>" + _helper(urls, _WAITING_AUDIO_CODE), 1)
        self.assertEqual(without_audio_helper(waiting), activity())
        self.assertEqual(without_audio_helper(queued), activity())
        self.assertEqual(without_audio_helper(earlier), activity())
        for existing in (waiting, queued, earlier):
            self.assertEqual(bind_interactive_audio(existing, urls, "room-1"), existing)
        rebound = bind_interactive_audio(earlier, urls, "room-1")
        self.assertEqual(rebound, earlier)
        self.assertNotIn("pending=cueId", earlier)
        with self.assertRaises(ValueError):
            without_audio_helper(earlier.replace("previous.pause();", "", 1))

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
        with self.assertRaisesRegex(ValueError, "override"):
            bind_interactive_audio(activity() + '<script>window.miraCancelNarration=()=>{};</script>', urls, "room-1")
        guarded = activity() + "<script>if (typeof window.miraNarrate === 'function') window.miraNarrate('find-cat');</script>"
        self.assertIn('id="mira-pre-recorded-audio"', bind_interactive_audio(guarded, urls, "room-1"))

    def test_ambiguous_duplicate_invalid_inventory_is_rejected(self):
        invalid = [activity() + activity(), activity([{"id": "same", "text": "一"}, {"id": "same", "text": "二"}]),
                   activity([{ "id": "../escape", "text": "一"}]), activity().replace('application/json', 'text/javascript'),
                   activity().replace('"schemaVersion"', '"wrong"')]
        for html in invalid:
            with self.subTest(html=html[:120]), self.assertRaises(ValueError):
                interactive_cues(html)


if __name__ == "__main__":
    unittest.main()

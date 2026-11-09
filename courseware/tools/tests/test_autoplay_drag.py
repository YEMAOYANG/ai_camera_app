"""Browser regression for building a quantity, then choosing an answer.

Opt in with MIRA_BROWSER_TESTS=1: this launches Chrome and never calls a provider.
The synthetic page deliberately has a separate reset control, reversible drags,
and anonymous picture choices. The bot must discover the intermediate state by
normal pointer events, complete it, and complete it again after replay.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from courseware.tools import autoplay


PAGE = '''<!doctype html><html><style>
#play{width:1280px;height:720px;position:relative}
.bin{position:absolute;top:100px;width:450px;height:180px;border:2px solid}
#a{left:20px}#b{left:700px}
.piece{width:60px;height:60px;margin:10px;cursor:grab;touch-action:none}
#choices{position:absolute;top:400px;left:300px;display:flex;gap:20px}
.answer{width:140px;height:100px;cursor:pointer}
.dot{display:inline-block;width:16px;height:16px;border-radius:50%;background:#555;margin:3px}
#reset{position:absolute;top:400px;left:40px;width:90px;height:90px}
.gone{display:none}#finish{position:absolute;inset:0;background:white}
</style><div id="dots"><i></i></div><span id="star-n">0</span><div id="say"></div>
<div id="play"><div class="bin" id="a"></div><div class="bin" id="b"></div>
<button id="reset">↶</button><div id="choices"></div></div>
<div id="finish" class="gone"><button id="btn-again">Again</button></div>
<script>
window.K={drags:[]};let selected=new Set(),held=null;
function draw(){
  K.drags=[];a.replaceChildren();b.replaceChildren();choices.replaceChildren();
  for(let i=0;i<6;i++){
    const e=document.createElement('button');e.id='piece-'+i;e.className='piece';
    const target=selected.has(i)?a:b;(selected.has(i)?b:a).append(e);
    e.onpointerdown=()=>{held={i,target}};
    K.drags.push({el:e,options:{targets:()=>[target]}});
  }
  for(let n=2;n<=4;n++){
    const e=document.createElement('button');e.className='answer';e.id='choice-'+n;
    for(let i=0;i<n;i++){const dot=document.createElement('i');dot.className='dot';e.append(dot)}
    e.onclick=()=>{
      if(selected.size===3 && n===3){document.querySelector('#finish').classList.remove('gone')}
    };choices.append(e);
  }
}
window.addEventListener('pointerup',event=>{
  if(!held)return;const r=held.target.getBoundingClientRect();
  if(event.clientX>=r.left&&event.clientX<=r.right&&event.clientY>=r.top&&event.clientY<=r.bottom){
    selected.has(held.i)?selected.delete(held.i):selected.add(held.i);draw();
  }held=null;
});
reset.onclick=()=>{selected.clear();draw()};
document.querySelector('#btn-again').onclick=()=>{
  document.querySelector('#finish').classList.add('gone');selected.clear();draw();
};draw();
</script></html>'''


RECORD_PAGE = '''<!doctype html><html><style>
#play{width:1280px;height:720px}button{width:100px;height:70px;margin:8px}
.gone{display:none}#finish{position:absolute;inset:0;background:white}
</style><div id="dots"><i></i></div><span id="star-n">0</span><div id="say"></div>
<div id="play"><div id="choices">
<button id="choice-a">●</button><button id="choice-b">■</button><button id="choice-c">▲</button>
</div><button id="reset" aria-label="重新整理小书">↺</button><div id="record"></div></div>
<div id="finish" class="gone"><button id="btn-again">Again</button></div>
<script>
let step=0,busy=false;const order=['choice-a','choice-c','choice-b'];
const say=document.getElementById('say');
for(const choice of document.querySelectorAll('#choices button'))choice.onclick=()=>{
  if(busy||choice.id!==order[step])return;
  busy=true;say.className='ok';say.textContent='这一页整理好了';
  record.append(choice.textContent);
  setTimeout(()=>{busy=false;if(++step===order.length)finish.classList.remove('gone')},900);
};
function resetPage(){step=0;busy=false;record.textContent='';say.textContent='';finish.classList.add('gone')}
reset.onclick=resetPage;document.getElementById('btn-again').onclick=resetPage;
</script></html>'''


@unittest.skipUnless(os.environ.get('MIRA_BROWSER_TESTS') == '1', 'opt-in real Chrome regression')
class DragThenAnswerTests(unittest.TestCase):
    def test_intermediate_drag_quantity_then_choice_and_replay(self):
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        if not Path(chrome).exists() or not shutil.which('node'):
            self.skipTest('Chrome and node are required')
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, 'scene-01.html').write_text(PAGE, encoding='utf-8')
            result = subprocess.run([
                shutil.which('node'), str(autoplay.BOT), '--playwright', str(autoplay._playwright_dir()),
                '--chrome', chrome, '--dir', temporary, '--max-steps', '200', '--seed', '7',
            ], capture_output=True, text=True, timeout=240, check=True)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]['errors'], [])
        self.assertIsNone(report[0]['stuck'])
        self.assertEqual(len(report[0]['finishes']), 2)

    def test_repeated_success_progress_and_separate_reset(self):
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        if not Path(chrome).exists() or not shutil.which('node'):
            self.skipTest('Chrome and node are required')
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, 'scene-01.html').write_text(RECORD_PAGE, encoding='utf-8')
            command = [shutil.which('node'), str(autoplay.BOT), '--playwright', str(autoplay._playwright_dir()),
                       '--chrome', chrome, '--dir', temporary, '--max-steps', '36', '--seed', '7']
            inspect = subprocess.run(command + ['--inspect', '1'], capture_output=True, text=True,
                                     timeout=30, check=True)
            candidates = json.loads(inspect.stdout)[0]['snapshot']['candidates']
            self.assertEqual({item['id'] for item in candidates}, {'choice-a', 'choice-b', 'choice-c'})
            played = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
        result = json.loads(played.stdout)[0]
        self.assertEqual(result['errors'], [])
        self.assertIsNone(result['stuck'])
        self.assertEqual(len(result['finishes']), 2)


if __name__ == '__main__':
    unittest.main()

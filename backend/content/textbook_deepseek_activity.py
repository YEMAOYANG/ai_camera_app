"""Picture-book pages rendered from preserved DeepSeek text, with no text fallback.

The renderer owns controls and interaction state, not teaching copy. Every
spoken string is a finite cue supplied by the compiler. Raster atlases retain
their original bytes; crop rectangles are viewport coordinates only.
"""
from html import escape
from pathlib import Path

from content import textbook_activity_templates as t
from content.textbook_catalog import canonical


def frozen_js(value):
    """Saved JSON key order must not change an exact-template admission check."""
    return canonical(value).replace("</", "<\\/")


STYLE = """
.shell{max-width:1120px;padding:16px 24px;background:#fffaf0}.lesson-page{max-width:1000px;margin:auto}
.picture-book{display:flex;justify-content:center;gap:32px;align-items:center}
.art{position:relative;overflow:hidden;isolation:isolate;min-width:0;background:#f5eddb;border-radius:12px;aspect-ratio:var(--art-aspect)}
.art img{position:absolute;max-width:none;pointer-events:none;user-select:none}.main-art{width:min(100%,calc(300px * var(--art-aspect)));margin:0;flex-shrink:1}
.art-window{position:absolute;inset:0;overflow:hidden;border-radius:inherit}.art.has-glyph{overflow:visible;margin-top:36px;margin-bottom:22px}
.art .target-glyph{position:absolute;transform:translate(-50%,-50%);font:clamp(30px,5vw,52px)/1.1 'Kaiti SC','STKaiti',serif;background:#fffcf0e8;color:#304c44;padding:3px 8px;border-radius:7px;box-shadow:0 1px 4px #44351d30}
.character{font-family:'Kaiti SC','STKaiti',serif;font-size:clamp(64px,13vw,128px);color:#304c44;line-height:1.1;min-width:1em;text-align:center;flex-shrink:0}
.picture-answers{display:grid;grid-template-columns:repeat(var(--answers),minmax(0,1fr));gap:18px;margin:18px auto;max-width:850px}
.picture-answers button{position:relative;padding:5px;border:3px solid transparent;background:#fffdf7;border-radius:16px;min-width:56px;min-height:100px;box-shadow:0 2px 8px #65583118}
.picture-answers button.selected{outline:0;border-color:#638568}.picture-answers button.wrong-picture{outline:3px dashed #b38c5c}
.picture-answers .feedback-mark{position:absolute;right:8px;bottom:8px;width:40px;height:40px;border-radius:50%;background:#648768;color:white;display:grid;place-items:center;font-size:30px}
.page-meter{display:flex;gap:6px;justify-content:center;margin:8px auto}.page-meter i{width:7px;height:7px;border-radius:50%;background:#ded8c8}.page-meter i.active{background:#af8244;transform:scale(1.4)}
.lesson-tools{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin:16px auto}.lesson-tools button{min-height:56px;border-radius:50%;width:60px;border-color:#d9d0ba}.lesson-tools button span{display:none}.lesson-tools #page-start{background:#f4ca65;border-color:#e2b345}.lesson-tools #page-next{background:#e1ead9}
.oral-wait{display:flex;align-items:center;justify-content:center;height:30px;gap:9px}.oral-wait i{width:7px;height:12px;border-radius:6px;background:#ba9562;animation:breath 1.4s ease-in-out infinite alternate}.oral-wait i:nth-child(2){height:24px;animation-delay:.3s}.oral-wait i:nth-child(3){height:16px;animation-delay:.6s}@keyframes breath{to{opacity:.25;transform:scaleY(.65)}}
.lesson-video{width:100%;max-height:330px;height:auto;aspect-ratio:16/9}.model-book{position:relative;max-width:960px;margin:auto}.model-book canvas{width:100%;height:clamp(220px,44vh,370px);touch-action:none;border-radius:18px}.role-labels{position:absolute;inset:0;pointer-events:none}.role-labels span{position:absolute;font-family:'Kaiti SC','STKaiti',serif;font-size:38px;background:#fffaf0ed;border-radius:50%;width:48px;height:48px;text-align:center;transform:translate(-50%,-100%);box-shadow:0 3px 7px #344a3b20}
@media(max-width:600px){.shell{padding:10px}.picture-book{gap:8px}.main-art{width:min(100%,calc(250px * var(--art-aspect)))}.picture-answers{gap:8px;margin:12px auto}.picture-answers button{padding:3px;min-height:90px}.lesson-tools{gap:7px;margin:10px auto}.lesson-tools button{width:56px}.character{font-size:72px}}
.main-art{width:min(100%,calc(clamp(96px,100dvh - 180px,300px) * var(--art-aspect)))}
.art.has-glyph{margin-top:24px;margin-bottom:10px}
.art.has-floating-glyph{margin-top:58px}.art .floating-glyph{transform:translate(-50%,-100%)}
.note:empty{display:none}
.model-book canvas{height:clamp(150px,100dvh - 215px,370px)}
.model-book+.picture-answers{max-width:420px;margin:8px auto}
.model-book+.picture-answers .art{width:clamp(64px,16dvh,110px);margin-inline:auto}
@media(min-width:700px){.lesson-page:has(.picture-answers){display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:24px;align-items:center;min-height:240px}.lesson-page:has(.picture-answers) .picture-book{gap:16px}.lesson-page:has(.picture-answers) .main-art{width:min(100%,calc(clamp(96px,100dvh - 190px,230px) * var(--art-aspect)))}.lesson-page:has(.picture-answers) .character{font-size:clamp(64px,9vw,112px)}.picture-answers{width:100%;margin:8px auto;gap:10px}.picture-answers button .art{max-width:calc(170px * var(--art-aspect));margin-inline:auto}}
@media(max-height:540px){.lesson-tools{margin:8px auto}.shell{padding:8px 12px}.lesson-video{height:calc(100dvh - 120px);max-height:330px;min-height:120px}}
@media(max-width:699px){.lesson-page:has(.picture-answers) .main-art{width:min(100%,calc(clamp(64px,(100dvh - 180px) * .4,160px) * var(--art-aspect)))}.lesson-page:has(.picture-answers) .character{font-size:64px}.picture-answers .art{max-width:calc(clamp(70px,(100dvh - 180px) * .4,160px) * var(--art-aspect));margin-inline:auto}.art .target-glyph{font-size:30px}}
"""


def picture(asset, *, main=False, overlays=()):
    x, y, width, height = asset.get("crop", [0, 0, 1, 1])
    ratio = asset["width"] * width / (asset["height"] * height)
    style = f"left:{-100*x/width:.8g}%;top:{-100*y/height:.8g}%;width:{100/width:.8g}%;height:{100/height:.8g}%"
    glyphs = ''.join(f'<span class="target-glyph{" floating-glyph" if overlay["y"] < .15 else ""}" style="left:{overlay["x"]*100:.8g}%;top:{overlay["y"]*100:.8g}%">'
                     + escape(overlay["character"]) + '</span>' for overlay in overlays)
    floating = any(overlay["y"] < .15 for overlay in overlays)
    return (f'<div class="art{" main-art" if main else ""}{" has-glyph" if overlays else ""}{" has-floating-glyph" if floating else ""}" style="--art-aspect:{ratio:.8g}" role="img" '
            f'aria-label="{escape(asset["description"], quote=True)}"><div class="art-window"><img alt="" draggable="false" '
            f'src="{escape(asset["src"], quote=True)}" style="{style}"></div>{glyphs}</div>')


PAGER = r"""
const pages=PAGES;let pageIndex=0,pageEpoch=0,started=false,settled=false,modelAvailable=false,attemptTimer=null,spokenShots=new Set();
const pageNodes=Array.from(document.querySelectorAll('.lesson-page'));
function refreshControls(){
  const p=pages[pageIndex];
  document.getElementById('page-start').disabled=interactionBusy;
  document.getElementById('page-replay').disabled=interactionBusy||!started;
  document.getElementById('page-hint').disabled=interactionBusy||!started||!p.retryCueId;
  document.getElementById('page-model').disabled=interactionBusy||!modelAvailable;
  document.getElementById('page-model').hidden=p.kind!=='oral_response';
  document.getElementById('page-hint').hidden=!p.retryCueId;
  document.getElementById('page-previous').disabled=interactionBusy||pageIndex===0;
  document.getElementById('page-next').disabled=interactionBusy||!settled||pageIndex===pages.length-1;
  pageNodes[pageIndex].querySelectorAll('[data-answer]').forEach(b=>{b.disabled=interactionBusy||!started||settled;});
}
function showPage(index){
  cancelOperation();clearTimeout(attemptTimer);attemptTimer=null;pageEpoch++;pageIndex=index;started=false;settled=false;modelAvailable=false;spokenShots=new Set();
  pageNodes.forEach((n,i)=>{n.hidden=i!==index;n.querySelectorAll('.selected,.wrong-picture').forEach(b=>b.classList.remove('selected','wrong-picture'));n.querySelectorAll('.feedback-mark').forEach(b=>b.remove());});
  document.querySelectorAll('[data-page-dot]').forEach((n,i)=>n.classList.toggle('active',i===index));
  document.getElementById('oral-wait').hidden=true;note.textContent='';refreshControls();
  document.documentElement.scrollTop=0;document.body.scrollTop=0;
}
async function speakOptional(id,signal){if(id)await narrate(id,signal);}
function begin(){run(async(signal)=>{
  const p=pages[pageIndex],epoch=pageEpoch;started=true;clearTimeout(attemptTimer);modelAvailable=false;
  await narrate(p.teacherCueId,signal);await speakOptional(p.promptCueId,signal);
  if(p.kind==='oral_response'){
    document.getElementById('oral-wait').hidden=false;
    attemptTimer=setTimeout(()=>{if(epoch!==pageEpoch||document.hidden)return;modelAvailable=true;settled=true;document.getElementById('oral-wait').hidden=true;refreshControls();},8000);
  }else if(p.videoSrc){document.getElementById(p.pageId+'-video').controls=true;}
  else if(p.kind==='observe'){await speakOptional(p.completeCueId,signal);settled=true;}
});}
function answer(choiceId){
  if(interactionBusy||!started||settled)return;
  const p=pages[pageIndex],choice=p.choices.find(c=>c.choiceId===choiceId);if(!choice)return;
  run(async signal=>{
    const selected=document.getElementById(choice.buttonId),correct=p.correctChoiceIds.includes(choiceId);
    selected.classList.add(correct?'selected':'wrong-picture');
    if(correct){settled=true;selected.insertAdjacentHTML('beforeend','<span class="feedback-mark" aria-label="这幅图符合问题">✓</span>');}
    await narrate(choice.feedbackCueId,signal);
    if(correct)await speakOptional(p.completeCueId,signal);else selected.classList.remove('wrong-picture');
  });
}
document.querySelectorAll('[data-answer]').forEach(b=>b.addEventListener('click',()=>answer(b.dataset.answer)));
listen('page-start',begin);listen('page-replay',()=>{const p=pages[pageIndex];run(s=>narrate(p.promptCueId||p.teacherCueId,s));});
listen('page-hint',()=>{assisted=true;const p=pages[pageIndex];if(p.retryCueId)run(s=>narrate(p.retryCueId,s));});
listen('page-model',()=>{if(!modelAvailable)return;assisted=true;run(async s=>{await narrate(pages[pageIndex].modelCueId,s);await speakOptional(pages[pageIndex].completeCueId,s);});});
listen('page-previous',()=>{if(pageIndex>0)showPage(pageIndex-1);});listen('page-next',()=>{if(settled&&pageIndex<pages.length-1)showPage(pageIndex+1);});
document.querySelectorAll('.lesson-video').forEach(v=>{
  const readShot=()=>{if(!started){v.pause();return;}if(interactionBusy||v.paused)return;const p=pages[pageIndex],shots=p.videoShots||[],index=shots.findIndex(s=>v.currentTime>=s.start&&v.currentTime<s.end);if(index<0||spokenShots.has(index))return;
    const epoch=pageEpoch;spokenShots.add(index);run(async signal=>{try{await narrate(shots[index].cueId,signal);if(epoch===pageEpoch&&!document.hidden){setInteractionBusy(false);await v.play();}}catch(error){spokenShots.delete(index);throw error;}});
  };
  v.addEventListener('play',readShot);v.addEventListener('timeupdate',readShot);
  v.addEventListener('ended',()=>{if(!started||interactionBusy)return;const p=pages[pageIndex];if(spokenShots.size!==(p.videoShots||[]).length)return;run(async signal=>{await speakOptional(p.completeCueId,signal);settled=true;});});
});
function applyTeacherState(state){if(Object.keys(state).length===1&&state.sceneStateId==='reset'){assisted=true;showPage(0);}}
document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(attemptTimer);attemptTimer=null;document.getElementById('oral-wait').hidden=true;}});
showPage(0);
"""


def pages_scene(scene, assets):
    body = '<style>' + STYLE + '</style>'
    for index, page in enumerate(scene["pages"]):
        body += f'<section id="{escape(page["pageId"], quote=True)}" class="lesson-page" {"hidden" if index else ""}>'
        if page.get("videoSrc"):
            body += (f'<video id="{escape(page["pageId"], quote=True)}-video" class="lesson-video" controls playsinline preload="metadata" '
                     f'src="{escape(page["videoSrc"], quote=True)}"></video>')
        elif page.get("hideMainArt"):
            body += '<div class="character">' + escape(" ".join(page["targetCharacters"])) + '</div>'
        else:
            body += '<div class="picture-book">' + picture(assets[page["assetKey"]], main=True, overlays=page.get("glyphOverlays", []))
            if page["targetCharacters"]:
                body += '<div class="character">' + escape(" ".join(page["targetCharacters"])) + '</div>'
            body += '</div>'
        if page["choices"]:
            body += f'<div class="picture-answers" style="--answers:{len(page["choices"])}">'
            for choice in page["choices"]:
                body += (f'<button type="button" id="{escape(choice["buttonId"], quote=True)}" data-answer="{escape(choice["choiceId"], quote=True)}" '
                         f'data-mira-picture-choice="{escape(choice["assetKey"])}" aria-label="{escape(assets[choice["assetKey"]]["description"], quote=True)}">'
                         + picture(assets[choice["assetKey"]], overlays=choice.get("glyphOverlays", [])) + '</button>')
            body += '</div>'
        body += '</section>'
    body += '<div class="page-meter" aria-label="本段学习进度">' + ''.join('<i data-page-dot></i>' for _ in scene["pages"]) + '</div>'
    body += '<div id="oral-wait" class="oral-wait" aria-label="先自己说一说" hidden><i></i><i></i><i></i></div><div class="lesson-tools">'
    for identity, label, icon in (("previous", "上一幅", "left"), ("start", "听老师讲", "start"),
                                  ("replay", "再听问题", "replay"), ("hint", "听提示", "hint"),
                                  ("model", "听老师示范", "speaker"), ("next", "下一幅", "next")):
        body += t.button("page-" + identity, label, icon)
    body += '</div>'
    return t.scene_html(scene, body, PAGER.replace("PAGES", frozen_js(scene["pages"])))


ROLE_CONTROLS = r"""
const config=CONFIG;let garden=null,current=0,ready=false,attempt=null,roleEpoch=0;
function refreshControls(){
  document.getElementById('role-model').disabled=interactionBusy||!ready;
  document.querySelectorAll('[data-role-config]').forEach(b=>b.disabled=interactionBusy||!garden);
}
function selectRole(index){
  if(!garden||interactionBusy)return;current=index;roleEpoch++;clearTimeout(attempt);ready=false;
  const row=config.configurations[current],epoch=roleEpoch;garden.setRoles(row,false);
  document.querySelectorAll('[data-role-config]').forEach((b,i)=>b.classList.toggle('selected',i===current));
  run(async signal=>{await narrate(row.teacherCueId,signal);await narrate(row.questionCueId,signal);
    attempt=setTimeout(()=>{if(epoch!==roleEpoch||document.hidden)return;ready=true;refreshControls();},8000);
  });
}
listen('role-start',()=>run(async signal=>{await narrate(config.teacherCueId,signal);if(config.promptCueId)await narrate(config.promptCueId,signal);}));
listen('role-replay',()=>run(signal=>narrate(config.configurations[current].questionCueId,signal)));
listen('role-model',()=>{if(!ready||!garden)return;garden.reveal();assisted=true;run(async signal=>{await narrate(config.configurations[current].modelCueId,signal);if(config.completeCueId)await narrate(config.completeCueId,signal);});});
listen('role-rotate',()=>{if(garden)garden.rotate();});listen('role-reset',()=>{if(garden)garden.reset();});
document.querySelectorAll('[data-role-config]').forEach((b,i)=>b.addEventListener('click',()=>selectRole(i)));
function applyTeacherState(state){if(Object.keys(state).length===1&&state.sceneStateId==='reset'&&garden){assisted=true;garden.reset();}}
try{garden=makeRoleGarden(document.getElementById('role-canvas'),document.getElementById('role-labels'));garden.setRoles(config.configurations[0],false);}catch(error){document.getElementById('role-canvas').hidden=true;note.textContent='立体画面暂时没有打开，请重新进入这一页。';}
document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(attempt);attempt=null;}else if(garden)garden.reset();});
refreshControls();
"""


def role_scene(scene, assets):
    body = '<style>' + STYLE + '</style><div class="model-book"><canvas id="role-canvas" aria-label="可以拖动旋转的立体花园"></canvas><div id="role-labels" class="role-labels"></div></div>'
    body += '<div class="picture-answers" style="--answers:3">'
    for index, row in enumerate(scene["roleModel"]["configurations"]):
        body += (f'<button type="button" data-role-config="{index}" aria-label="换这位小朋友说话">'
                 + picture(assets[row["portraitAssetKey"]]) + '</button>')
    body += '</div><div class="lesson-tools">'
    for identity, label, icon in (("start", "听玩法", "start"), ("replay", "再听问题", "replay"),
                                  ("model", "看角色听示范", "speaker"), ("rotate", "转一转", "rotate"),
                                  ("reset", "回到正面", "reset")):
        body += t.button("role-" + identity, label, icon)
    body += '</div>'
    geometry = Path(__file__).with_name("textbook_role_garden.js").read_text(encoding="utf-8")
    code = geometry + '\n' + ROLE_CONTROLS.replace("CONFIG", frozen_js(scene["roleModel"]))
    return t.scene_html(scene, body, code)

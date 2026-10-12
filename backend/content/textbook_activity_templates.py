"""Deterministic activity templates; no arbitrary input HTML or JavaScript is executed.

Extracted from the previously browser exercised original compiler (source SHA
55664a1ffd5c1cb6931e2abe8096ccd69fa933e950078a9342ac3bba6afba3e6). The fixed templates are now owned and versioned with the backend.
"""
from html import escape
import json
import xml.etree.ElementTree as ET

FIT_CSS = """.choices>button{min-width:56px}.shell{min-width:0}.model{height:150px;min-height:150px}.choices>button svg{max-height:70px}.tools{gap:5px}.tools button{min-width:56px;min-height:56px}video{height:clamp(120px,36vh,230px);min-height:120px;max-height:230px}.wrong-picture{outline:4px dashed #b58c61}.progress{display:flex;gap:7px;margin:5px 0}.progress i{display:block;width:16px;height:16px;border:2px solid #739482;border-radius:50%}.progress i.done{background:#739482}@media(max-width:360px){.choices>button{flex-basis:70px;max-width:none}.tools button span{font-size:12px}}"""

# A bounded, centered task area uses three substantial picture targets on wide
# stages. Narrow layouts preserve all three distinguishable pictures and 56px
# targets; teacher controls may wrap rather than shrinking the lesson.
TASK_CSS = """
.shell{max-width:1120px;padding:14px}.choices{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));max-width:900px;gap:14px;margin:12px auto;align-items:stretch}.choices>button{width:100%;max-width:none;min-width:56px;min-height:118px;padding:10px;background:#fffdf7;border:2px solid #b9cec2;box-shadow:0 3px 0 #d8dfd1}.choices>button svg{width:100%;max-height:142px}.tools{justify-content:center;gap:9px;margin:10px auto;max-width:960px}.tools button{min-width:56px;min-height:56px}.target-row{justify-content:center;gap:18px}.target{width:188px;height:154px;min-width:56px}.pair{justify-content:center;min-height:112px;position:relative;padding:8px}.pair>svg{width:128px;height:104px}.pair.paired{background:#e2eee1;border:4px solid #588b79}.pair .feedback-mark{width:56px;height:56px;flex-shrink:0}.picture-detail{margin:8px auto}.progress{justify-content:center;gap:14px;margin:12px auto}.progress i{width:22px;height:22px;border-width:3px}.progress i.done{background:#739482;border-color:#42685d}.note{text-align:center}.model,video{margin-inline:auto;max-width:960px}.route{max-width:1040px;margin:auto}.route button{min-height:148px}.route svg{height:108px}
@media(max-width:600px){.shell{padding:8px}.choices{gap:7px;margin:8px auto}.choices>button{padding:5px;min-height:90px}.choices>button svg{max-height:100px}.target-row{gap:8px}.target{width:144px;height:120px}.pair>svg{width:94px;height:82px}.pair .feedback-mark{width:40px;height:40px}.tools{gap:6px}.tools button span{display:none}.progress{margin:8px auto}.route svg{height:94px}}
@media(max-width:360px){.choices>button{min-height:84px}.choices>button svg{max-height:82px}.pair>svg{width:82px;height:72px}.target-row{gap:5px}.target{width:128px;height:108px}}
@media(max-height:480px){.shell{padding:8px}.target{width:158px;height:120px}.pair{min-height:90px;padding:5px}.pair>svg{width:112px;height:90px}.choices{margin:8px auto;gap:9px}.choices>button{min-height:96px;padding:6px}.choices>button svg{max-height:100px}.tools{margin:7px auto;gap:6px}.progress{margin:8px auto}.note{margin:3px 0}}
.choices>button .feedback-mark{width:44px;height:44px;max-height:44px;margin:3px auto}.pair.paired,.choices>button.selected{animation:picture-confirm 180ms ease-out}.wrong-pair,.wrong-picture{animation:picture-retry 180ms ease-out}@keyframes picture-confirm{from{transform:scale(.97)}to{transform:scale(1)}}@keyframes picture-retry{0%,100%{transform:translateX(0)}35%{transform:translateX(-4px)}70%{transform:translateX(4px)}}@media(prefers-reduced-motion:reduce){.pair.paired,.choices>button.selected,.wrong-pair,.wrong-picture{animation:none}}
"""

def js(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


ICONS = {
    "speaker": '<path d="M10 25h12l15-13v40L22 39H10Z" fill="currentColor"/><path d="M45 20q17 12 0 24m5-30q24 18 0 36" fill="none" stroke="currentColor" stroke-width="4"/>',
    "start": '<path d="m22 13 26 19-26 19Z" fill="currentColor"/>',
    "replay": '<path d="M46 23a19 19 0 1 0 3 23M46 23V11m0 12H34" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round"/>',
    "next": '<path d="M12 32h38M35 16l16 16-16 16" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round"/>',
    "reset": '<path d="M16 22a19 19 0 1 1-2 24M16 22V10m0 12h12" fill="none" stroke="currentColor" stroke-width="6"/>',
    "hint": '<circle cx="28" cy="27" r="16" fill="none" stroke="currentColor" stroke-width="5"/><path d="m40 40 16 16" stroke="currentColor" stroke-width="7"/>',
    "left": '<path d="M52 32H13m15-16L12 32l16 16" fill="none" stroke="currentColor" stroke-width="6"/>',
    "right": '<path d="M12 32h39M36 16l16 16-16 16" fill="none" stroke="currentColor" stroke-width="6"/>',
    "rotate": '<path d="M45 20a19 19 0 1 0 5 22M45 20v-9m0 9H34" fill="none" stroke="currentColor" stroke-width="6"/>',
    "separate": '<path d="M22 13v38H9V13Zm33 0v38H42V13Z" fill="currentColor"/><path d="M29 32H3m8-8-8 8 8 8m24-8h26m-8-8 8 8-8 8" fill="none" stroke="#b27b4c" stroke-width="4"/>',
    "join": '<path d="M19 13h12v38H19Zm14 0h12v38H33Z" fill="currentColor"/><path d="M2 32h15m-7-8 8 8-8 8m52-8H47m7-8-8 8 8 8" fill="none" stroke="#b27b4c" stroke-width="4"/>',
    "pencil": '<path d="M13 7h33v48H13Z" fill="none" stroke="currentColor" stroke-width="4"/><path d="m26 43 5-14L51 9l8 8-20 20Z" fill="#c69b61" stroke="currentColor" stroke-width="3"/>',
}


def button(identity, label, icon, extra=""):
    return (f'<button type="button" id="{escape(identity)}" aria-label="{escape(label)}" {extra}>'
            f'<svg viewBox="0 0 64 64" aria-hidden="true">{ICONS[icon]}</svg><span>{escape(label)}</span></button>')


CSS = """
html,body{margin:0;min-width:0;max-width:100%;overflow-x:hidden;background:#f7f3e8;color:#294744;font-family:system-ui,sans-serif}*{box-sizing:border-box}
.shell{width:100%;max-width:1100px;margin:auto;padding:10px;min-width:0}.tools,.choices{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
button{min-width:56px;min-height:56px;flex-shrink:0;touch-action:manipulation;border:2px solid #c3d5cc;border-radius:14px;background:#fffdf5;color:#294744;padding:6px;cursor:pointer;font:inherit}button:disabled{opacity:.55;cursor:default}button svg{width:30px;height:30px;vertical-align:middle}button span{font-size:14px;margin:0 4px}button:focus-visible{outline:4px solid #be8b47;outline-offset:2px}
.choices>button{flex:1 1 86px;max-width:180px;min-width:0;min-height:72px}.choices>button svg{display:block;width:100%;height:auto;max-height:104px}.choices>button span{display:block}.selected{outline:4px solid #588b79;outline-offset:1px}.teacher-hint{outline:4px solid #be8b47;outline-offset:3px}
video,.model{display:block;width:100%;height:42vh;max-height:280px;min-height:120px;object-fit:contain;border-radius:16px;background:#dce9e5}video{background:#213933}.route{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,132px),1fr));gap:8px}.route button{min-height:130px}.route svg{width:100%;height:95px}.route span{display:block}.target-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.target{width:130px;height:115px;border:3px solid #aec9b9;border-radius:16px;background:#fff;touch-action:none}.target svg{width:100%;height:100%;display:block}.target.armed{outline:4px solid #be8b47}.pair{display:flex;gap:8px;min-height:82px;align-items:center}.pair svg{width:100px;height:80px}.wrong-pair{border:3px dashed #b89673;border-radius:12px}.paired{border:3px solid #588b79;border-radius:12px}.picture-detail{max-width:280px}.picture-detail svg{width:100%;height:160px}.note{font-size:16px;line-height:1.4;margin:6px 0;min-height:22px}#teacher-note{background:#fff4cc;padding:8px;border-radius:10px}.ghost{position:fixed;width:90px;height:80px;pointer-events:none;opacity:.85;z-index:20;transform:translate(-50%,-50%)}[hidden]{display:none!important}
@media(max-width:420px){.shell{padding:8px}.choices>button{flex-basis:80px}.choices>button svg{max-height:85px}.tools{gap:6px}.tools button{padding:5px}.tools button span{font-size:12px}.route{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:320px){.route{grid-template-columns:1fr}.choices{align-items:stretch}.choices>button{max-width:none;flex-basis:70px}}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


COMMON = r"""
const root=document.getElementById('activity-root'), note=document.getElementById('student-note');
let operation=0, activeController=null, interactionBusy=false, assisted=false, lastCue=null;
const videos=Array.from(document.querySelectorAll('video'));
function setInteractionBusy(value){interactionBusy=value;videos.forEach(v=>{v.controls=!value;});document.querySelectorAll('button').forEach(b=>{b.disabled=value&&!b.hasAttribute('data-cancel');});if(typeof refreshControls==='function')refreshControls();}
function cancelOperation(){if(typeof clearDrag==='function')clearDrag();operation++;if(activeController)activeController.abort();activeController=null;videos.forEach(v=>v.pause());setInteractionBusy(false);}
async function run(action){cancelOperation();const token=operation,controller=new AbortController();activeController=controller;setInteractionBusy(true);try{return await action(controller.signal,token);}catch(error){if(token===operation)note.textContent='可以再试一次，或点重听。';return false;}finally{if(token===operation){activeController=null;setInteractionBusy(false);}}}
function waitCue(id,signal){let cleanup=()=>{};const promise=new Promise((resolve,reject)=>{let done=false,timer;const finish=(error)=>{if(done)return;done=true;cleanup();error?reject(error):resolve(true);};const onState=e=>{const d=e.detail;if(!d||d.cueId!==id)return;if(d.status==='ready')finish();else if(d.status==='error'||d.status==='missing'||d.status==='hidden')finish(new Error('audio-unavailable'));};const abort=()=>finish(new Error('cancelled'));cleanup=()=>{clearTimeout(timer);window.removeEventListener('mira-narration-state',onState);signal.removeEventListener('abort',abort);};window.addEventListener('mira-narration-state',onState);signal.addEventListener('abort',abort,{once:true});timer=setTimeout(()=>finish(new Error('audio-timeout')),45000);if(signal.aborted)abort();});promise.catch(()=>{});return {promise,cancel:cleanup};}
async function narrate(id,signal){if(signal.aborted)throw new Error('cancelled');const wait=waitCue(id,signal);lastCue=id;try{const started=await dispatchCue(id);if(started!==true)throw new Error('audio-not-started');await wait.promise;if(signal.aborted||document.hidden)throw new Error('cancelled');if(typeof onCueCompleted==='function')onCueCompleted(id);return true;}finally{wait.cancel();}}
function listen(id,fn){document.getElementById(id).addEventListener('click',fn);}
function replay(){run(async signal=>{if(lastCue)await narrate(lastCue,signal);});}
const allowedTargets=new Set(Array.from(document.querySelectorAll('[id]')).map(e=>e.id));
function knownTarget(value){if(typeof value!=='string')return null;const id=value.startsWith('#')?value.slice(1):value;return allowedTargets.has(id)?document.getElementById(id):null;}
window.addEventListener('message',event=>{if(event.source!==window.parent)return;const data=event.data;if(!data||typeof data!=='object'||Array.isArray(data))return;if(data.type==='MIRA_NARRATION_VISIBILITY'){if(data.visible===false)cancelOperation();else if(typeof resizeModel==='function')resizeModel();return;}if(data.type==='SET_WIDGET_STATE'){if(data.state&&typeof data.state==='object'&&!Array.isArray(data.state))applyTeacherState(data.state);return;}if(data.type==='HIGHLIGHT_ELEMENT'){document.querySelectorAll('.teacher-hint').forEach(e=>e.classList.remove('teacher-hint'));const target=knownTarget(data.target);if(target)target.classList.add('teacher-hint');return;}if(data.type==='ANNOTATE_ELEMENT'){const target=knownTarget(data.target);if(target&&target.id==='teacher-note'&&typeof data.content==='string'){target.textContent=data.content.slice(0,160);target.hidden=false;}return;}if(data.type==='REVEAL_ELEMENT'){const target=knownTarget(data.target);if(target&&(target.id==='teacher-note'||target.id==='observation-help'))target.hidden=false;}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)cancelOperation();else if(typeof resizeModel==='function')resizeModel();});
"""


def scene_html(design, body, code):
    cues = [{"id": cue["cueId"], "text": cue["teacherText"]} for cue in design["finiteCues"]]
    calls = "function dispatchCue(id){switch(id){" + "".join(
        f"case {js(cue['id'])}:return window.miraNarrate({js(cue['id'])});" for cue in cues
    ) + "default:return Promise.resolve(false);}}"
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="mira-responsive-activity" content="low-reading-v1">'
            f'<title>{escape(design["title"])}</title><style>{CSS + FIT_CSS + TASK_CSS}</style></head><body>'
            '<main id="activity-root" class="shell"><div id="teacher-note" hidden></div>'
            '<div id="observation-help" hidden>点重听，听完再看看图片。</div>' + body +
            '<p id="student-note" class="note" aria-live="polite"></p></main>'
            '<script type="application/json" id="mira-narration-cues">' +
            js({"schemaVersion": "mira.interactive.narration-cues.v1", "cues": cues}) + '</script><script>"use strict";\n' +
            calls + '\n' + COMMON + '\n' + code + '\n</script></body></html>')


def picture_button(identity, asset_id, svg, label="", extra=""):
    accessible_label = label or ET.fromstring(svg).get("aria-label") or "观察这幅图片"
    return (f'<button type="button" id="{escape(identity)}" data-mira-picture-choice="{escape(asset_id)}" '
            f'aria-label="{escape(accessible_label, quote=True)}" {extra}>{svg}' +
            (f'<span>{escape(label)}</span>' if label else '') + '</button>')


def video_scene(scene, assets):
    observations = scene["observations"]
    body = '<video id="observation-video" controls playsinline preload="metadata" src="' + escape(scene['requiredVideoElement']['src'], quote=True) + '"></video>' + '<div class="choices">' + ''.join(
        picture_button('observe-' + ob["assetId"], ob["assetId"], assets[ob["assetId"]],
                       extra=f'data-view="{escape(ob["assetId"])}"') for ob in observations) + '</div><div class="tools">'
    body += button('start', '开始看', 'start', 'data-cancel') + button('replay', '重听', 'replay', 'data-cancel')
    body += button('again', '再看一次', 'reset', 'data-cancel') + button('finish', '听老师小结', 'speaker') + '</div>'
    code = r"""
const video=document.querySelector('video'), views=OBSERVATIONS;let observed=new Set();
function refreshControls(){}
function mediaWait(test,events,signal,change){return new Promise((resolve,reject)=>{let done=false,timer;const finish=error=>{if(done)return;done=true;clearTimeout(timer);events.forEach(e=>video.removeEventListener(e,check));video.removeEventListener('error',failed);signal.removeEventListener('abort',abort);error?reject(error):resolve(true);};const check=()=>{if(test())finish();};const failed=()=>finish(new Error('video-error'));const abort=()=>finish(new Error('cancelled'));events.forEach(e=>video.addEventListener(e,check));video.addEventListener('error',failed);signal.addEventListener('abort',abort,{once:true});timer=setTimeout(()=>finish(new Error('video-timeout')),12000);if(signal.aborted){abort();return;}try{if(change)change();check();}catch(error){finish(error);}});}
async function seekFrame(seconds,signal){video.pause();video.preload='auto';if(video.readyState<1)await mediaWait(()=>video.readyState>=1,['loadedmetadata','loadeddata'],signal,()=>video.load());await mediaWait(()=>!video.seeking&&Math.abs(video.currentTime-seconds)<.15&&video.readyState>=2,['seeked','loadeddata','canplay'],signal,()=>{video.currentTime=seconds;});}
function observe(view){if(interactionBusy)return;run(async signal=>{await seekFrame(view.seekSeconds,signal);document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('selected',b.dataset.view===view.assetId));await narrate(view.cueId,signal);observed.add(view.assetId);});}
function start(again){run(async signal=>{await seekFrame(0,signal);await narrate(again?REPLAY_CUE:INTRO_CUE,signal);setInteractionBusy(false);await video.play();});}
views.forEach(v=>listen('observe-'+v.assetId,()=>observe(v)));listen('start',()=>start(false));listen('again',()=>start(true));listen('replay',replay);listen('finish',()=>{if(interactionBusy)return;run(signal=>narrate(FINISH_CUE,signal));});
function applyTeacherState(state){const keys=Object.keys(state);if(keys.some(k=>!['videoView','sceneStateId'].includes(k))||keys.length!==1)return;if(state.sceneStateId==='reset'){assisted=true;start(true);return;}const view=views.find(v=>v.assetId===state.videoView);if(view){assisted=true;observe(view);}}
""".replace('OBSERVATIONS', js(observations)).replace('REPLAY_CUE', js(scene['replayCueId'])).replace('INTRO_CUE', js(scene['initialCueId'])).replace('FINISH_CUE', js(scene['finishCueId']))
    return scene_html(scene, body, code)


WEBGL = r"""
const canvas=document.getElementById('model-canvas');let gl=null,program,buffer,positionLocation,colorLocation,matrixLocation;
let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};
function identity(){return new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);}
function multiply(a,b){const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];return o;}
function translate(x,y,z){const m=identity();m[12]=x;m[13]=y;m[14]=z;return m;}
function rotateY(a){const c=Math.cos(a),s=Math.sin(a);return new Float32Array([c,0,-s,0,0,1,0,0,s,0,c,0,0,0,0,1]);}
function rotateX(a){const c=Math.cos(a),s=Math.sin(a);return new Float32Array([1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1]);}
function scale(x,y,z){const m=identity();m[0]=x;m[5]=y;m[10]=z;return m;}
function orthographic(aspect){const width=Math.max(3.4,1.9*aspect),height=width/aspect;const m=identity();m[0]=1/width;m[5]=1/height;m[10]=-.05;return m;}
const meshes=[];
function triangle(out,a,b,c,color,light){[a,b,c].forEach(v=>out.push(v[0],v[1],v[2],color[0]*light,color[1]*light,color[2]*light));}
function box(){const out=[],v=[[-.5,-.5,-.5],[.5,-.5,-.5],[.5,.5,-.5],[-.5,.5,-.5],[-.5,-.5,.5],[.5,-.5,.5],[.5,.5,.5],[-.5,.5,.5]];[[0,1,2,3],[4,7,6,5],[0,4,5,1],[3,2,6,7],[0,3,7,4],[1,5,6,2]].forEach((q,i)=>{const c=[1,1,1],l=.65+i*.06;triangle(out,v[q[0]],v[q[1]],v[q[2]],c,l);triangle(out,v[q[0]],v[q[2]],v[q[3]],c,l);});return out;}
function sphere(){const out=[];for(let y=0;y<10;y++)for(let x=0;x<16;x++){const p=(i,j)=>{const a=i*Math.PI/10,b=j*Math.PI*2/16;return [Math.sin(a)*Math.cos(b)*.5,Math.cos(a)*.5,Math.sin(a)*Math.sin(b)*.5];};const a=p(y,x),b=p(y+1,x),c=p(y+1,x+1),d=p(y,x+1),l=.65+.3*(1-y/10);triangle(out,a,b,c,[1,1,1],l);triangle(out,a,c,d,[1,1,1],l);}return out;}
function cylinder(){const out=[];for(let i=0;i<16;i++){const a=i*Math.PI/8,b=(i+1)*Math.PI/8,p=[Math.cos(a)*.5,-.5,Math.sin(a)*.5],q=[Math.cos(b)*.5,-.5,Math.sin(b)*.5],r=[q[0],.5,q[2]],s=[p[0],.5,p[2]];triangle(out,p,q,r,[1,1,1],.75);triangle(out,p,r,s,[1,1,1],.75);triangle(out,[0,.5,0],s,r,[1,1,1],1);triangle(out,[0,-.5,0],q,p,[1,1,1],.6);}return out;}
const geometries={box:box(),sphere:sphere(),cylinder:cylinder()};
function part(group,shape,x,y,z,sx,sy,sz,color,ry=0,rx=0){meshes.push({group,shape,color,local:multiply(translate(x,y,z),multiply(rotateY(ry),multiply(rotateX(rx),scale(sx,sy,sz))))});}
function createScene(){
part('ground','box',0,-.12,0,7,.18,3.4,[.78,.83,.68]);part('stand','cylinder',0,.13,0,1.1,.3,1.1,[.62,.55,.42]);
part('tree','cylinder',0,.9,0,.25,1.8,.25,[.47,.31,.19]);
part('tree','cylinder',-.28,1.35,0,.13,.8,.13,[.47,.31,.19],0,-.65);part('tree','cylinder',.3,1.25,.04,.13,.8,.13,[.47,.31,.19],0,.65);
part('tree','sphere',-.42,1.95,0,1.05,.8,.9,[.42,.62,.35]);part('tree','sphere',.4,1.9,.06,1.05,.8,.9,[.48,.68,.38]);part('tree','sphere',0,2.25,0,.8,.7,.8,[.5,.71,.4]);
part('bird','sphere',0,.9,0,.85,.55,.52,[.36,.55,.66]);part('bird','sphere',.42,1.2,0,.42,.42,.4,[.36,.55,.66]);part('bird','box',.69,1.2,0,.3,.1,.14,[.85,.63,.33]);
part('bird','sphere',-.05,.95,.32,.62,.13,.4,[.62,.75,.8],-.3);part('bird','sphere',-.05,.95,-.32,.62,.13,.4,[.62,.75,.8],.3);part('bird','box',-.5,.85,0,.48,.1,.26,[.71,.58,.34],.4);part('bird','sphere',.5,1.29,.18,.07,.07,.07,[.12,.17,.16]);part('bird','sphere',.5,1.29,-.18,.07,.07,.07,[.12,.17,.16]);
[-.18,.18].forEach(z=>part('bird','cylinder',.06,.45,z,.05,.5,.05,[.43,.34,.22]));
part('field','box',0,.15,0,1.65,.25,1.35,[.64,.49,.29]);[-.45,0,.45].forEach(z=>{part('field','box',0,.32,z,1.5,.13,.16,[.77,.62,.38]);[-.5,0,.5].forEach(x=>{part('field','cylinder',x,.54,z,.04,.36,.04,[.3,.5,.25]);part('field','sphere',x-.08,.67,z,.22,.06,.1,[.4,.64,.31],0,.6);part('field','sphere',x+.08,.71,z,.22,.06,.1,[.44,.68,.34],0,-.6);});});
}
function compile(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error('shader');return s;}
function initModel(){try{gl=canvas.getContext('webgl',{antialias:true,alpha:false});if(!gl)throw new Error('webgl');program=gl.createProgram();gl.attachShader(program,compile(gl.VERTEX_SHADER,'attribute vec3 position;attribute vec3 color;uniform mat4 matrix;varying vec3 tint;void main(){gl_Position=matrix*vec4(position,1.0);tint=color;}'));gl.attachShader(program,compile(gl.FRAGMENT_SHADER,'precision mediump float;varying vec3 tint;void main(){gl_FragColor=vec4(tint,1.0);}'));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('program');buffer=gl.createBuffer();positionLocation=gl.getAttribLocation(program,'position');colorLocation=gl.getAttribLocation(program,'color');matrixLocation=gl.getUniformLocation(program,'matrix');createScene();document.getElementById('model-retry').hidden=true;resizeModel();requestAnimationFrame(renderLoop);}catch(error){gl=null;document.getElementById('model-retry').hidden=false;note.textContent='点图形按钮，再试一次。';}}
function resizeModel(){if(!gl)return;const r=canvas.getBoundingClientRect(),ratio=Math.min(window.devicePixelRatio||1,2);if(r.width<1||r.height<1)return;canvas.width=Math.round(r.width*ratio);canvas.height=Math.round(r.height*ratio);gl.viewport(0,0,canvas.width,canvas.height);drawModel();}
function drawModel(){if(!gl)return;gl.enable(gl.DEPTH_TEST);gl.clearColor(.86,.91,.87,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(program);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.enableVertexAttribArray(positionLocation);gl.enableVertexAttribArray(colorLocation);gl.vertexAttribPointer(positionLocation,3,gl.FLOAT,false,24,0);gl.vertexAttribPointer(colorLocation,3,gl.FLOAT,false,24,12);const view=multiply(orthographic(canvas.width/canvas.height),multiply(rotateX(.35),multiply(rotateY(-.35),translate(0,-.9,0))));meshes.forEach(m=>{const p=poses[m.group]||{x:0,z:0,angle:0};const world=multiply(translate(p.x,0,p.z),multiply(rotateY(p.angle),m.local));const data=geometries[m.shape].slice();for(let i=0;i<data.length;i+=6){data[i+3]*=m.color[0];data[i+4]*=m.color[1];data[i+5]*=m.color[2];}gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);gl.uniformMatrix4fv(matrixLocation,false,multiply(view,world));gl.drawArrays(gl.TRIANGLES,0,data.length/6);});}
function renderLoop(){if(gl&&!document.hidden)drawModel();requestAnimationFrame(renderLoop);}
new ResizeObserver(resizeModel).observe(canvas);window.addEventListener('resize',resizeModel);
"""



VISIBLE_MATCH_CODE = r"""
const config=CONFIG, source=document.getElementById('source'), pair=document.getElementById('pair'), choices=document.getElementById('choices'),detail=document.getElementById('detail');let round=0,matched=false,feedbackReady=false,armed=false,started=false,ghost=null;
function refreshControls(){document.getElementById('next').disabled=interactionBusy||!matched||!feedbackReady;document.querySelectorAll('[data-option]').forEach(b=>{b.disabled=interactionBusy||matched||!started;});source.disabled=interactionBusy||matched||!started;document.getElementById('hint').disabled=interactionBusy||!started;}
function onCueCompleted(id){if(matched&&id===config.rounds[round].matchCueId){feedbackReady=true;updateProgress();}}
function clearDrag(){if(ghost)ghost.remove();ghost=null;}
function renderRound(){clearDrag();const r=config.rounds[round];source.innerHTML=config.crops[r.targetAssetId];source.classList.remove('armed');pair.innerHTML='';pair.className='pair';detail.hidden=true;matched=false;feedbackReady=false;armed=false;document.querySelectorAll('[data-option]').forEach(b=>{b.hidden=!r.optionAssetIds.includes(b.dataset.option);b.classList.remove('selected');});r.optionAssetIds.forEach(key=>choices.appendChild(document.getElementById('option-'+key)));updateProgress();refreshControls();}
function begin(reset){run(async signal=>{round=0;started=true;renderRound();await narrate(reset?config.reset:config.intro,signal);await narrate(config.rounds[round].instructionCueId,signal);});}
function choose(key){if(interactionBusy||matched||!started||!armed||!config.rounds[round].optionAssetIds.includes(key))return;run(async signal=>{const r=config.rounds[round];pair.innerHTML=config.crops[r.targetAssetId]+config.assets[key];if(key!==r.targetAssetId){pair.className='pair wrong-pair';await narrate(config.retry,signal);return;}matched=true;pair.className='pair paired';pair.insertAdjacentHTML('beforeend','<svg class="feedback-mark" viewBox="0 0 64 64" aria-label="图片已经配好"><circle cx="32" cy="32" r="28" fill="#588b79"/><path d="m16 32 11 11 22-24" fill="none" stroke="#fffdf5" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>');document.getElementById('option-'+key).classList.add('selected');await narrate(r.matchCueId,signal);});}
source.addEventListener('click',()=>{if(!interactionBusy&&started&&!matched){armed=true;source.classList.add('armed');}});
source.addEventListener('pointerdown',event=>{if(interactionBusy||!started||matched)return;armed=true;source.classList.add('armed');ghost=document.createElement('div');ghost.className='ghost';ghost.innerHTML=source.innerHTML;document.body.appendChild(ghost);ghost.style.left=event.clientX+'px';ghost.style.top=event.clientY+'px';source.setPointerCapture(event.pointerId);});
source.addEventListener('pointermove',event=>{if(ghost){ghost.style.left=event.clientX+'px';ghost.style.top=event.clientY+'px';}});
function endDrag(event){if(ghost){ghost.remove();ghost=null;const target=document.elementFromPoint(event.clientX,event.clientY);const option=target&&target.closest('[data-option]');if(option)choose(option.dataset.option);}}
source.addEventListener('pointerup',endDrag);source.addEventListener('pointercancel',()=>{if(ghost)ghost.remove();ghost=null;});
document.querySelectorAll('[data-option]').forEach(b=>b.addEventListener('click',()=>choose(b.dataset.option)));
listen('start',()=>begin(false));listen('reset',()=>begin(true));listen('replay',replay);listen('hint',()=>{if(interactionBusy)return;run(async signal=>{detail.innerHTML=source.innerHTML;detail.hidden=false;await narrate(config.hint,signal);});});
listen('next',()=>{if(interactionBusy||!matched||!feedbackReady)return;run(async signal=>{if(round===config.rounds.length-1){await narrate(config.complete,signal);return;}round++;renderRound();await narrate(config.rounds[round].instructionCueId,signal);});});
function applyTeacherState(state){const keys=Object.keys(state);if(keys.length!==1||keys.some(k=>!['roundId','sceneStateId'].includes(k)))return;if(state.sceneStateId==='reset'){assisted=true;begin(true);return;}const next=config.rounds.findIndex(r=>r.roundId===state.roundId);if(next<0||interactionBusy)return;assisted=true;run(async signal=>{round=next;started=true;renderRound();await narrate(config.rounds[round].instructionCueId,signal);});}
renderRound();
"""

LISTEN_MATCH_CODE = r"""
const config=CONFIG;let round=0,started=false,matched=false,feedbackReady=false;
function refreshControls(){document.getElementById('next').disabled=interactionBusy||!matched||!feedbackReady;document.querySelectorAll('[data-answer]').forEach(b=>b.disabled=interactionBusy||!started||matched);}
function onCueCompleted(id){if(matched&&id===config.rounds[round].matchCueId){feedbackReady=true;updateProgress();}}
function renderRound(){matched=false;feedbackReady=false;const r=config.rounds[round],choices=document.getElementById('choices');document.getElementById('target-character').textContent=r.targetCharacter||'';document.querySelectorAll('[data-answer]').forEach(b=>{b.hidden=!r.optionAssetIds.includes(b.dataset.answer);b.classList.remove('selected','wrong-picture');b.querySelectorAll('.feedback-mark').forEach(e=>e.remove());});r.optionAssetIds.forEach(k=>choices.appendChild(document.getElementById('answer-'+k)));updateProgress();refreshControls();}
function begin(reset){run(async signal=>{round=0;started=true;renderRound();await narrate(reset?config.reset:config.intro,signal);await narrate(config.rounds[round].instructionCueId,signal);});}
function choose(key){if(interactionBusy||!started||matched||!config.rounds[round].optionAssetIds.includes(key))return;run(async signal=>{const b=document.getElementById('answer-'+key);if(key!==config.rounds[round].targetAssetId){b.classList.add('wrong-picture');await narrate(config.rounds[round].retryCueId||config.retry,signal);b.classList.remove('wrong-picture');return;}matched=true;b.classList.add('selected');b.insertAdjacentHTML('beforeend','<svg class="feedback-mark" viewBox="0 0 64 64" aria-label="图片找对了"><circle cx="32" cy="32" r="28" fill="#588b79"/><path d="m16 32 11 11 22-24" fill="none" stroke="#fffdf5" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>');await narrate(config.rounds[round].matchCueId,signal);});}
document.querySelectorAll('[data-answer]').forEach(b=>b.addEventListener('click',()=>choose(b.dataset.answer)));
function replayRound(){run(signal=>narrate(started?(matched?config.rounds[round].matchCueId:config.rounds[round].instructionCueId):config.intro,signal));}
listen('start',()=>begin(false));listen('reset',()=>begin(true));listen('replay',replayRound);listen('next',()=>{if(interactionBusy||!matched||!feedbackReady)return;run(async signal=>{if(round===config.rounds.length-1){await narrate(config.complete,signal);return;}round++;renderRound();await narrate(config.rounds[round].instructionCueId,signal);});});
function applyTeacherState(state){if(Object.keys(state).length!==1)return;if(state.sceneStateId==='reset'){assisted=true;begin(true);return;}const i=config.rounds.findIndex(r=>r.roundId===state.roundId);if(i<0||interactionBusy)return;assisted=true;run(async signal=>{round=i;started=true;renderRound();await narrate(config.rounds[round].instructionCueId,signal);});}
renderRound();
"""

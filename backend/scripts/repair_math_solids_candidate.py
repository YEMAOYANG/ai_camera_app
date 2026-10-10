#!/usr/bin/env python3
"""Author a private, traceable derivative of one failed grade-one candidate.

No provider calls, database writes, runtime registration, audio or publication.
Original generation input and diagnostics are opened read-only.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.textbook_catalog import digest
from content.textbook_interactive_narration import interactive_cues
from services.textbook_batch_audio import narration_workload

REPO = Path(__file__).resolve().parents[2]
TASK = "e43307857c3cc88692d6bb37a58f9104628e28eac86fa68d95a64060d30be9f0"
CLASSROOM = "solids_e433_derived_v1"
BASE = REPO / "output/textbook-full-audit-20261009"
SOURCE = BASE / "private-generation-v2" / TASK
RAW = REPO / "openmaic-runtime/.runtime/OpenMAIC/data/textbook-batch-diagnostics" / TASK / "akHLRVG5-9"
DESIGN = BASE / "alignment-audit/pep-math-g1-upper-solids-design.json"
VIDEO = BASE / "original-media/solids-desk-observation-v1.mp4"
VIDEO_SHA = "08f97381e158045e9dee23494336e1387f5198ed487629c0b0f3caad5adb55c5"


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def svg(shape, life=False, transfer=False):
    """Independently drawn, text-free perspective pictures, not emoji glyphs."""
    colors = ("#ca7950", "#a955a0", "#55a69a", "#e0a33b")
    color = colors[["cuboid", "cube", "cylinder", "sphere"].index(shape)]
    if transfer:
        color = {"sphere": "#6584ba", "cube": "#6b9d66", "cylinder": "#cb855d", "cuboid": "#7f8daa"}[shape]
    if not life:
        color='#8eabc2'
    base = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 160" role="img">'
    base += '<ellipse cx="100" cy="139" rx="69" ry="11" fill="#233442" opacity=".10"/>'
    if shape == "sphere":
        base += f'<defs><radialGradient id="shade"><stop stop-color="#fff3cd"/><stop offset=".5" stop-color="{color}"/><stop offset="1" stop-color="#a35d20"/></radialGradient></defs><circle cx="100" cy="82" r="53" fill="url(#shade)" stroke="#674626" stroke-width="2"/>'
        if life:
            base += '<path d="M64 42 Q116 66 130 125 M47 89 Q99 106 147 76" fill="none" stroke="#f9ecd2" stroke-width="5" opacity=".85"/>'
    elif shape == "cylinder":
        base += f'<ellipse cx="100" cy="119" rx="48" ry="18" fill="{color}" stroke="#36575a" stroke-width="2"/><path d="M52 43 V119 Q100 153 148 119 V43" fill="{color}" stroke="#36575a" stroke-width="2"/><ellipse cx="100" cy="43" rx="48" ry="18" fill="#b6d8cc" stroke="#36575a" stroke-width="2"/>'
        if life:
            base += '<path d="M58 61 Q100 82 142 61 M58 98 Q100 119 142 98" fill="none" stroke="#f4e8d4" stroke-width="9"/><ellipse cx="100" cy="41" rx="35" ry="10" fill="#dce7df"/>'
    else:
        # Three shared-edge polygons form a valid box; cube projected edges
        # have matching side lengths, cuboid has a visibly longer front edge.
        if shape == "cube":
            a,b,c,d,e,f,g = "48,49","100,23","152,49","100,75","48,111","100,137","152,111"
        else:
            a,b,c,d,e,f,g = "24,55","65,32","176,62","135,85","24,103","135,133","176,110"
        base += f'<polygon points="{a} {b} {c} {d}" fill="#e4c3a1" stroke="#684c48" stroke-width="2"/><polygon points="{a} {d} {f} {e}" fill="{color}" stroke="#684c48" stroke-width="2"/><polygon points="{d} {c} {g} {f}" fill="#79596e" stroke="#684c48" stroke-width="2"/>'
        if life and shape == "cube":
            base += '<path d="M74 64 V124 M74 36 L126 62 V124" fill="none" stroke="#f9e5b6" stroke-width="7"/>'
        elif life:
            base += '<path d="M35 70 L124 94 M77 47 L155 68" fill="none" stroke="#efd0a3" stroke-width="5"/>'
    base+='</svg>'
    if not life:
        for warm,cool in {'#a35d20':'#566f87','#fff3cd':'#e7eff4','#b6d8cc':'#c3d4dd','#e4c3a1':'#c3d4dd','#79596e':'#657e91'}.items():
            base=base.replace(warm,cool)
    return base


REPLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8H2V3M3 8a9 9 0 1 1 0 8"/></svg>'
NEXT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h15M13 5l7 7-7 7"/></svg>'
HINT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 17h8M9 21h6M8 14a7 7 0 1 1 8 0v2H8z"/></svg>'
CSS = """
*{box-sizing:border-box}body{margin:0;font:18px 'Microsoft YaHei',sans-serif;color:#304146;background:#f7f9fc}
.shell{max-width:1100px;margin:auto;padding:16px 24px;min-height:100vh;background:linear-gradient(#f8fbfb 0 76%,#ead8be 76%)}
h1{font-size:27px;margin:0 0 10px;line-height:1.3}button{font:inherit;touch-action:manipulation;min-width:48px;min-height:48px;border:2px solid #98b4b2;border-radius:15px;background:#fff;color:#304146;cursor:pointer;padding:8px 16px}
button:focus-visible,canvas:focus-visible{outline:4px solid #244f93;outline-offset:3px}button svg.control{width:25px;height:25px;fill:none;stroke:currentColor;stroke-width:2}button:disabled{opacity:.55;cursor:default}
.tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0}.tools svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:2;vertical-align:middle}
.note{min-height:28px;margin:8px 0;font-size:20px}.board{background:#fffdf8;border:3px solid #d3c2a8;border-radius:24px;padding:15px;box-shadow:0 6px 0 #c7ac87}
.reference{display:flex;align-items:center;gap:20px;justify-content:center;min-height:120px}.reference svg{width:150px;height:115px}.choices{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:15px 0}
.picture{display:flex;align-items:center;justify-content:center;position:relative;min-height:170px;border:3px solid #a9bcb9;border-radius:20px;background:#fff;padding:12px;touch-action:none}.picture svg{width:100%;height:150px;pointer-events:none}
.picture.selected{border-color:#43846e;background:#edf7f0}.picture.retry{outline:4px solid #ba835c}.picture.armed{outline:4px solid #426a91}.home{background:#f8f8f1}.home .placed-object{position:absolute;right:4px;bottom:0;width:72px;height:60px;pointer-events:none}
.moving{position:fixed!important;z-index:30;pointer-events:none;opacity:.85;width:170px!important;height:150px!important;min-height:150px!important;margin:0;transform:translate(-50%,-50%)}
.collection{display:flex;gap:10px;min-height:60px;margin-top:12px}.collection .group{display:flex;border:2px solid #d3c6b0;border-radius:12px;background:#fffdf8}.collection svg{width:58px;height:55px}
[hidden]{display:none!important}.canvas-wrap{position:relative;border:3px solid #a9bcb9;border-radius:20px;background:#f0f3ec;overflow:hidden;height:450px}.canvas-wrap canvas{display:block;width:100%;height:100%;touch-action:none}.ref-mini{position:absolute;left:14px;top:12px;background:#fffdf8dd;border-radius:14px;pointer-events:none}.ref-mini svg{width:125px;height:100px}
.model-buttons{display:flex;gap:10px;flex-wrap:wrap}.model-buttons button{padding:2px 9px;background:#fffdf8}.model-buttons svg{width:85px;height:70px}.map{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.map button{min-height:130px}.map svg{width:100%;height:85px}.life-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
@media(max-width:600px){.shell{padding:12px}.choices{gap:8px}.picture{min-height:135px;padding:4px}.picture svg{height:120px}.canvas-wrap{height:360px}.life-grid{grid-template-columns:repeat(2,1fr)}.map button{padding:5px;font-size:16px}.tools{gap:6px}.reference{min-height:95px}.reference svg{height:95px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
"""


def cue_bundle(design, scene):
    unused={"ug.game.enter", "ug.3d.enter"}
    cues = [{"id": x["cueId"].replace(".", "_"), "text": x["teacherText"]}
            for x in design["finiteCues"] if x["sceneId"] == scene and x['cueId'] not in unused]
    for cue in cues:
        if cue['id']=='ug_3d_complete':
            cue['text']='刚才我们观察了模型，还换了摆法。去生活里再找一找。'
    manifest = '<script type="application/json" id="mira-narration-cues">' + json.dumps(
        {"schemaVersion": "mira.interactive.narration-cues.v1", "cues": cues}, ensure_ascii=False) + "</script>"
    # Literal calls let both the native validator and the saved audio inventory
    # establish an exact finite cue mapping. Never install browser speech.
    cases = "\n".join(f"case {json.dumps(c['id'])}: return window.miraNarrate({json.dumps(c['id'])});" for c in cues)
    js = "const cueText=" + json.dumps({c["id"]: c["text"] for c in cues}, ensure_ascii=False) + ";\n"
    js += "let currentCue='';function playCue(id){currentCue=id;document.querySelector('#note').textContent=cueText[id]||'';try{switch(id){" + cases + "}}catch(_){document.documentElement.dataset.audioPending='true';return false;}}\n"
    js += "function showCue(id){currentCue=id;document.querySelector('#note').textContent=cueText[id]||'';}\n"
    js += "function stableTargetId(target){if(typeof target!=='string'||!/^#?[A-Za-z][A-Za-z0-9_-]*$/.test(target))return null;return target.replace(/^#/,'');}function highlightTarget(target){const id=stableTargetId(target);if(!id)return;const node=document.getElementById(id);if(!node)return;node.dataset.miraHighlighted='true';node.style.outline='4px solid #426a91';node.focus?.();setTimeout(()=>{delete node.dataset.miraHighlighted;node.style.outline='';},1400);}\n"
    return manifest, js


def html_page(title, body, manifest, js, module=False):
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><style>' + CSS + '</style></head><body><main class="shell"><h1>' + title + '</h1>' + body + '</main>' + manifest + '<script' + (' type="module"' if module else '') + '>' + js + '</script></body></html>'


def controls(extra=""):
    return '<div class="tools"><button id="replay" aria-label="再听一次">' + REPLAY + ' 再听</button><button id="hint" aria-label="给我提示">' + HINT + ' 提示</button><button id="reset" aria-label="重新开始">重来</button>' + extra + '</div><p id="note" class="note" aria-live="polite"></p>'


def game_html(design):
    manifest, js = cue_bundle(design, "ug_solids_game")
    rounds = design["scenes"][1]["rounds"]
    art = {s: {"model": svg(s), "primary": svg(s, True), "transfer": svg(s, True, True)} for s in ("sphere", "cube", "cylinder", "cuboid")}
    first = "".join('<button class="picture" data-mira-picture-choice="' + s + '" data-shape="' + s + '" aria-label="物品图片">' + art[s]["primary"] + '</button>' for s in ("cube", "sphere", "cylinder"))
    body = controls('<button id="next" hidden aria-label="继续">' + NEXT + ' 继续</button>') + '<section class="board"><div id="reference" class="reference">' + art["sphere"]["model"] + '</div><div id="tapChoices" class="choices">' + first + '</div><div id="dragItem" class="reference" hidden></div><div id="homes" class="choices" hidden></div></section><div id="collection" class="collection" aria-label="已收好的形状朋友"></div>'
    js += "const rounds=" + json.dumps(rounds, ensure_ascii=False) + ";const art=" + json.dumps(art, ensure_ascii=False) + ";\n"
    js += r"""
const state={roundIndex:0,phase:'tap',selectedAssetId:null,assignmentByAssetId:{},revealedCollection:[],hintRequested:false,teacherDemoRequested:false,armed:false};
const $=id=>document.getElementById(id);const safe=id=>id.replaceAll('.','_');const round=()=>rounds[state.roundIndex];
function emit(){document.documentElement.dataset.miraState=JSON.stringify(state);window.parent.postMessage({type:'MIRA_WIDGET_STATE',state:{...state}},'*');}
function picture(shape,kind,extra=''){return '<button class="picture '+extra+'" data-mira-picture-choice="'+shape+'" data-shape="'+shape+'" aria-label="物品图片">'+art[shape][kind]+'</button>';}
function begin(index,speak=true){state.roundIndex=index;state.phase='tap';state.selectedAssetId=null;state.armed=false;render();const id=safe(round().tapState.entryCueId);if(speak)playCue(id);else showCue(id);emit();}
function renderCollection(){$('collection').innerHTML=state.revealedCollection.map(s=>'<div class="group">'+art[s].model+art[s].primary+art[s].transfer+'</div>').join('');}
function render(){const r=round();$('reference').innerHTML=art[r.targetShapeId].model;$('tapChoices').hidden=!['tap','tapMatched'].includes(state.phase);$('dragItem').hidden=!['drag','placed'].includes(state.phase);$('homes').hidden=!['drag','placed'].includes(state.phase);$('next').hidden=!['tapMatched','placed'].includes(state.phase);
 $('tapChoices').innerHTML=r.tapState.optionAssetIds.map(id=>{const s=id.replace('life_primary_','');return picture(s,'primary',state.phase==='tapMatched'&&s===r.targetShapeId?'selected':'');}).join('');
 $('tapChoices').querySelectorAll('button').forEach(b=>{b.disabled=state.phase!=='tap';b.onclick=()=>choose(b.dataset.shape,b);});
 if(['drag','placed'].includes(state.phase)){$('dragItem').innerHTML=picture(r.targetShapeId,'transfer',state.armed?'armed':'');const item=$('dragItem').querySelector('button');item.disabled=state.phase==='placed';item.onclick=()=>{if(state.phase!=='drag')return;state.armed=!state.armed;item.classList.toggle('armed',state.armed);emit();};item.onpointerdown=startDrag;
 $('homes').innerHTML=r.dragState.homeShapeIds.map(s=>picture(s,'model','home')).join('');$('homes').querySelectorAll('button').forEach(b=>{b.disabled=state.phase==='placed';b.onclick=()=>{if(state.armed)drop(b.dataset.shape,b);};});if(state.phase==='placed'){$('homes').querySelector('[data-shape="'+r.targetShapeId+'"]').insertAdjacentHTML('beforeend','<span class="placed-object">'+art[r.targetShapeId].transfer+'</span>');}}
 renderCollection();}
function wrong(shape,node){const id=round().tapState.wrongCueByShapeId[shape];if(id)playCue(safe(id));node?.classList.add('retry');setTimeout(()=>node?.classList.remove('retry'),650);emit();}
function choose(shape,node){if(state.phase!=='tap')return;if(shape!==round().targetShapeId){wrong(shape,node);return;}state.selectedAssetId='life_primary_'+shape;state.phase='tapMatched';render();playCue(safe(round().tapState.correctCueId));emit();}
function drop(shape,node){if(state.phase!=='drag')return;state.armed=false;if(shape!==round().dragState.correctHomeShapeId){render();wrong(shape,node);return;}state.assignmentByAssetId[round().dragState.draggableAssetId]=shape;state.revealedCollection.push(shape);state.phase='placed';render();playCue(safe(round().dragState.correctCueId));emit();}
let drag=null;
function startDrag(e){if(state.phase!=='drag')return;drag={x:e.clientX,y:e.clientY,source:e.currentTarget,clone:null,pointerId:e.pointerId};e.currentTarget.setPointerCapture(e.pointerId);}
window.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.pointerId)return;if(!drag.clone&&Math.hypot(e.clientX-drag.x,e.clientY-drag.y)>8){drag.clone=drag.source.cloneNode(true);drag.clone.classList.add('moving');drag.clone.removeAttribute('data-mira-picture-choice');document.body.append(drag.clone);}if(drag.clone){e.preventDefault();drag.clone.style.left=e.clientX+'px';drag.clone.style.top=e.clientY+'px';}},{passive:false});
window.addEventListener('pointerup',e=>{if(!drag||e.pointerId!==drag.pointerId)return;const d=drag;drag=null;if(!d.clone)return;d.clone.remove();d.source.onclick=null;setTimeout(()=>{if(d.source.isConnected)d.source.onclick=()=>{state.armed=!state.armed;d.source.classList.toggle('armed',state.armed);emit();};},0);const target=document.elementFromPoint(e.clientX,e.clientY)?.closest('#homes [data-shape]');if(target)drop(target.dataset.shape,target);else{state.armed=false;render();playCue(safe(round().tapState.retryCueId));emit();}});
window.addEventListener('pointercancel',()=>{drag?.clone?.remove();drag=null;state.armed=false;render();emit();});
$('next').onclick=()=>{if(state.phase==='tapMatched'){state.phase='drag';render();playCue(safe(round().dragState.entryCueId));emit();}else if(state.phase==='placed'){if(state.roundIndex<rounds.length-1)begin(state.roundIndex+1);else{state.phase='complete';$('tapChoices').hidden=true;$('dragItem').hidden=true;$('homes').hidden=true;$('next').hidden=true;playCue('ug_game_complete');emit();}}};
$('replay').onclick=()=>playCue(currentCue);$('hint').onclick=()=>{state.hintRequested=true;playCue(safe(round().tapState.hintCueId));emit();};$('reset').onclick=()=>{Object.assign(state,{roundIndex:0,phase:'tap',selectedAssetId:null,assignmentByAssetId:{},revealedCollection:[],hintRequested:false,teacherDemoRequested:false,armed:false});begin(0,false);playCue('ug_game_reset');};
window.addEventListener('message',event=>{if(event.source!==parent)return;const data=event.data;if(!data||typeof data.type!=='string')return;if(data.type==='SET_WIDGET_STATE'&&data.state){const index=rounds.findIndex(r=>r.roundId===data.state.roundId);if(index>=0){state.teacherDemoRequested=true;begin(index,false);}}else if(data.type==='HIGHLIGHT_ELEMENT'&&typeof data.target==='string'){highlightTarget(data.target);}});
begin(0,false);
"""
    return html_page("形状朋友回家", body, manifest, js)


def three_html(design):
    manifest, js = cue_bundle(design, "ug_solids_3d")
    bodies = ''.join('<button data-shape="' + s + '" aria-label="选择模型">' + svg(s) + '</button>' for s in ('sphere','cube','cylinder','cuboid'))
    body = controls('<button id="next" hidden aria-label="继续">' + NEXT + ' 继续</button><button id="turn" hidden aria-label="拖动把手或点一下转动圆柱">转一转</button><button id="move" hidden aria-label="把选好的模型搬到垫子">搬一搬</button>')
    body += '<section class="canvas-wrap"><canvas id="world" tabindex="0" aria-label="可选择、拖动、转动的立体模型"></canvas><div id="reference" class="ref-mini">' + svg('sphere', True) + '</div></section><div id="modelButtons" class="model-buttons">' + bodies + '</div><p id="loading" class="note">请稍等</p>'
    js += r"""
const $=id=>document.getElementById(id);const state={sceneStateId:'select_sphere',teachingStateId:'solid_select',selectedMeshId:null,objectPosition:{},objectOrientation:{},hintRequested:false,teacherDemoRequested:false,evidenceOrigin:'learner_observation',cameraPreset:'default'};let ready=false,selected=null,meshes={},renderer,scene,camera,THREE,mat,referenceBox,handle,queuedTeacherState=null;
function emit(){document.documentElement.dataset.miraState=JSON.stringify(state);window.parent.postMessage({type:'MIRA_WIDGET_STATE',state:{...state}},'*');}
function cue(id,speak=true){if(speak)playCue(id);else showCue(id);emit();}
function showButtons(){const mode=state.sceneStateId;$('next').hidden=!['sphere_selected','cylinder_turned','comparison_placed'].includes(mode);$('turn').hidden=mode!=='cylinder_placed';$('move').hidden=!['place_cylinder','compare_move'].includes(mode);}
function select(id){if(!ready)return;const mode=state.sceneStateId;if(mode==='select_sphere'){if(id!=='sphere'){cue('ug_3d_select_wrong_'+id);return;}state.selectedMeshId=id;state.sceneStateId='sphere_selected';meshes.sphere.material.emissive.setHex(0x234423);cue('ug_3d_select_ok');}
 else if(mode==='place_cylinder'){if(id!=='cylinder'){cue('ug_3d_place_wrong');return;}state.selectedMeshId=id;meshes.cylinder.material.emissive.setHex(0x234423);cue('ug_3d_place_prompt');}
 else if(mode==='compare_select'){if(id!=='cuboid'){cue('ug_3d_compare_wrong_'+id);return;}state.selectedMeshId=id;state.sceneStateId='compare_move';meshes.cuboid.material.emissive.setHex(0x234423);cue('ug_3d_compare_ok');}showButtons();}
function snapshot(){for(const [id,m] of Object.entries(meshes)){state.objectPosition[id]={x:m.position.x,y:m.position.y,z:m.position.z};state.objectOrientation[id]={x:m.rotation.x,y:m.rotation.y,z:m.rotation.z,quaternion:{x:m.quaternion.x,y:m.quaternion.y,z:m.quaternion.z,w:m.quaternion.w}};}emit();}
function placeDone(id){if(state.sceneStateId==='place_cylinder'&&id==='cylinder'){state.sceneStateId='cylinder_placed';handle.position.set(meshes.cylinder.position.x,meshes.cylinder.position.y+1.2,meshes.cylinder.position.z);handle.visible=true;cue('ug_3d_place_ok');}else if(state.sceneStateId==='compare_move'&&id==='cuboid'){state.sceneStateId='comparison_placed';cue('ug_3d_compare_placed');}showButtons();snapshot();}
function moveToMat(){if(!ready)return;const id=state.sceneStateId==='place_cylinder'?'cylinder':state.sceneStateId==='compare_move'?'cuboid':null;if(!id)return;if(state.selectedMeshId!==id){cue('ug_3d_place_prompt');return;}meshes[id].position.x=mat.position.x;meshes[id].position.z=mat.position.z;placeDone(id);}
function turnDoneIfHorizontal(){if(state.sceneStateId!=='cylinder_placed')return;const axis=new THREE.Vector3(0,1,0).applyQuaternion(meshes.cylinder.quaternion);if(Math.abs(axis.y)<=.06){state.sceneStateId='cylinder_turned';handle.visible=false;cue('ug_3d_turn_ok');showButtons();}}
function turnBy(delta){if(state.sceneStateId!=='cylinder_placed')return;meshes.cylinder.rotation.z=Math.min(Math.PI/2,Math.max(0,meshes.cylinder.rotation.z+delta));meshes.cylinder.position.y=.8*Math.cos(meshes.cylinder.rotation.z)+.5*Math.sin(meshes.cylinder.rotation.z);handle.position.set(meshes.cylinder.position.x,meshes.cylinder.position.y+1.2,meshes.cylinder.position.z);snapshot();turnDoneIfHorizontal();}
function initialTransforms(){const positions={sphere:[-3.2,.66,0],cube:[-1.05,.65,0],cylinder:[1.05,.8,0],cuboid:[3.3,.52,0]};for(const [id,m] of Object.entries(meshes)){m.position.set(...positions[id]);m.rotation.set(0,0,0);m.material.emissive.setHex(0);}}
function markTeacherDemo(){state.teacherDemoRequested=true;state.evidenceOrigin='teacher_demonstration';}
function enterTeachingState(id,{speak=true,assisted=false}={}){if(!ready||!['solid_select','solid_place','solid_compare'].includes(id))return false;if(assisted)markTeacherDemo();state.teachingStateId=id;state.selectedMeshId=null;for(const m of Object.values(meshes))m.material.emissive.setHex(0);handle.visible=false;referenceBox.visible=false;mat.visible=id!=='solid_select';
 if(id==='solid_select'){initialTransforms();state.sceneStateId='select_sphere';$('reference').innerHTML=ART.sphere;cue('ug_3d_select_prompt',speak);}
 else if(id==='solid_place'){state.sceneStateId='place_cylinder';meshes.cylinder.position.set(1.05,.8,0);meshes.cylinder.rotation.set(0,0,0);mat.position.set(2.5,.025,2);$('reference').innerHTML=ART.cylinder;cue('ug_3d_place_prompt',speak);}
 else{state.sceneStateId='compare_select';meshes.cylinder.position.set(-3.4,.5,2);meshes.cylinder.rotation.set(0,0,Math.PI/2);meshes.cuboid.position.set(2.9,.52,-.6);meshes.cuboid.rotation.set(0,0,0);referenceBox.visible=true;referenceBox.position.set(1.45,.6,2);mat.position.set(-.9,.025,2);$('reference').innerHTML=ART.cuboid;cue('ug_3d_compare_prompt',speak);}showButtons();snapshot();return true;}
function reset(speak=true){if(!ready){location.reload();return;}Object.assign(state,{hintRequested:false,teacherDemoRequested:false,evidenceOrigin:'learner_observation'});enterTeachingState('solid_select',{speak:false});if(speak)cue('ug_3d_reset');}
function finiteVector(value,keys){return value&&typeof value==='object'&&keys.every(k=>typeof value[k]==='number'&&Number.isFinite(value[k]));}
function applyObjectTransform(t){if(!t||typeof t!=='object'||Object.keys(t).some(k=>!['modelId','shapeId','objectId','position','quaternion'].includes(k)))return false;const id=t.modelId||t.shapeId||t.objectId;const allowed=(['place_cylinder','cylinder_placed'].includes(state.sceneStateId)&&id==='cylinder')||(state.sceneStateId==='compare_move'&&id==='cuboid');if(!allowed)return false;const p=t.position,q=t.quaternion;if(p&&(!finiteVector(p,['x','y','z'])||Math.abs(p.x)>5||Math.abs(p.z)>3.5||p.y<0||p.y>5))return false;if(q&&(!finiteVector(q,['x','y','z','w'])||Math.hypot(q.x,q.y,q.z,q.w)<.001))return false;if(!p&&!q)return false;const mesh=meshes[id],previous=mesh.position.clone(),before=state.sceneStateId;markTeacherDemo();state.selectedMeshId=id;
 if(p)mesh.position.set(p.x,p.y,p.z);if(q){const next=new THREE.Quaternion(q.x,q.y,q.z,q.w).normalize();const axis=new THREE.Vector3(0,1,0).applyQuaternion(next);if(before!=='place_cylinder'||Math.abs(axis.y)>.95)mesh.quaternion.copy(next);}mesh.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(mesh);mesh.position.y+=.03-box.min.y;mesh.updateMatrixWorld(true);
 if(before==='place_cylinder'||before==='compare_move'){if(Math.abs(mesh.position.x-mat.position.x)<1.15&&Math.abs(mesh.position.z-mat.position.z)<.85){mesh.position.x=mat.position.x;mesh.position.z=mat.position.z;placeDone(id);}else{mesh.position.copy(previous);cue(before==='place_cylinder'?'ug_3d_place_miss':'ug_3d_compare_ok');}}
 else{handle.position.set(mesh.position.x,mesh.position.y+1.2,mesh.position.z);turnDoneIfHorizontal();}snapshot();return true;}
function applyTeacherState(value){if(!value||typeof value!=='object')return;if(!ready){queuedTeacherState=value;return;}const aliases={solid_select:'solid_select',select_sphere:'solid_select',solid_place:'solid_place',place_cylinder:'solid_place',solid_compare:'solid_compare',compare_select:'solid_compare'};let entered=false;if(typeof value.sceneStateId==='string'&&aliases[value.sceneStateId])entered=enterTeachingState(aliases[value.sceneStateId],{assisted:true});else if(value.reset===true){entered=enterTeachingState(state.teachingStateId,{assisted:true});}
 if(typeof value.selectedShapeId==='string'&&Object.hasOwn(meshes,value.selectedShapeId)){markTeacherDemo();select(value.selectedShapeId);}if(value.objectTransform)applyObjectTransform(value.objectTransform);
 if(['front','side','top'].includes(value.cameraPreset)){markTeacherDemo();const positions={front:[0,5,13],side:[13,5,0],top:[.01,14,.01]};camera.position.set(...positions[value.cameraPreset]);camera.lookAt(0,0,.6);state.cameraPreset=value.cameraPreset;}
 if(typeof value.replayCueId==='string'&&Object.hasOwn(cueText,value.replayCueId)&&!entered&&!value.selectedShapeId&&!value.objectTransform){markTeacherDemo();cue(value.replayCueId);}snapshot();}
function highlightThreeTarget(target){const id=stableTargetId(target);if(!id)return;if(id==='solid-place-mat'&&ready&&mat.visible){markTeacherDemo();state.highlightedTarget=id;mat.material.emissive.setHex(0x426a91);setTimeout(()=>{mat.material.emissive.setHex(0);if(state.highlightedTarget===id)delete state.highlightedTarget;snapshot();},1400);snapshot();}else highlightTarget(target);}
const ART=ART_JSON;
$('replay').onclick=()=>playCue(currentCue);$('hint').onclick=()=>{state.hintRequested=true;cue(state.sceneStateId==='cylinder_placed'?'ug_3d_turn_prompt':'ug_3d_hint');};$('reset').onclick=()=>reset();$('turn').onclick=()=>turnBy(Math.PI/4);$('move').onclick=moveToMat;
$('modelButtons').querySelectorAll('[data-shape]').forEach(b=>b.onclick=()=>select(b.dataset.shape));
$('next').onclick=()=>{if(!ready)return;if(state.sceneStateId==='sphere_selected'){enterTeachingState('solid_place');}
 else if(state.sceneStateId==='cylinder_turned'){enterTeachingState('solid_compare');}
 else if(state.sceneStateId==='comparison_placed'){state.sceneStateId='complete';cue('ug_3d_complete');}showButtons();snapshot();};
window.addEventListener('message',event=>{if(event.source!==parent)return;const data=event.data;if(!data||typeof data.type!=='string')return;if(data.type==='SET_WIDGET_STATE')applyTeacherState(data.state);else if(data.type==='HIGHLIGHT_ELEMENT')highlightThreeTarget(data.target);});
showCue('ug_3d_select_prompt');emit();
try{
 THREE=await import('/vendor/three/0.160.0/three.module.js');scene=new THREE.Scene();scene.background=new THREE.Color('#f0f3ec');camera=new THREE.PerspectiveCamera(42,1,.1,100);camera.position.set(7.3,8.5,12.8);camera.lookAt(0,0,.6);
 renderer=new THREE.WebGLRenderer({canvas:$('world'),antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;
 scene.add(new THREE.HemisphereLight(0xffffff,0x8e8d7b,2.8));const sun=new THREE.DirectionalLight(0xffffff,3);sun.position.set(-5,10,5);sun.castShadow=true;scene.add(sun);
 const floor=new THREE.Mesh(new THREE.PlaneGeometry(16,10),new THREE.MeshStandardMaterial({color:0xe8dac3,roughness:.9}));floor.rotation.x=-Math.PI/2;floor.receiveShadow=true;scene.add(floor);
 const geometry={sphere:new THREE.SphereGeometry(.66,36,24),cube:new THREE.BoxGeometry(1.3,1.3,1.3),cylinder:new THREE.CylinderGeometry(.5,.5,1.6,36),cuboid:new THREE.BoxGeometry(2.3,1.04,1.2)};const colors={sphere:0xe0a33b,cube:0xa955a0,cylinder:0x55a69a,cuboid:0xca7950};
 for(const id of Object.keys(geometry)){const mesh=new THREE.Mesh(geometry[id],new THREE.MeshStandardMaterial({color:colors[id],roughness:.45}));mesh.castShadow=true;mesh.receiveShadow=true;mesh.userData.shape=id;meshes[id]=mesh;scene.add(mesh);}
 mat=new THREE.Mesh(new THREE.PlaneGeometry(2.5,1.9),new THREE.MeshStandardMaterial({color:0xb5d6d0,side:THREE.DoubleSide}));mat.rotation.x=-Math.PI/2;scene.add(mat);
 referenceBox=new THREE.Mesh(new THREE.BoxGeometry(2.3,1.2,1.2),new THREE.MeshStandardMaterial({color:0xbc8b56,roughness:.7}));referenceBox.castShadow=true;scene.add(referenceBox);
 handle=new THREE.Mesh(new THREE.TorusGeometry(.36,.09,10,36),new THREE.MeshStandardMaterial({color:0x426a91}));handle.userData.shape='turn_handle';scene.add(handle);
 const raycaster=new THREE.Raycaster(),mouse=new THREE.Vector2(),ground=new THREE.Plane(new THREE.Vector3(0,1,0),0),hit=new THREE.Vector3();let pointer=null;
 function ray(e){const rect=$('world').getBoundingClientRect();mouse.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(mouse,camera);}
 $('world').addEventListener('pointerdown',e=>{ray(e);const h=raycaster.intersectObjects([...Object.values(meshes),...(handle.visible?[handle]:[])],false)[0];if(!h)return;const id=h.object.userData.shape;pointer={id,x:e.clientX,y:e.clientY,lastX:e.clientX,moved:false,start:h.object.position.clone()};$('world').setPointerCapture(e.pointerId);});
 $('world').addEventListener('pointermove',e=>{if(!pointer)return;const p=pointer;if(Math.hypot(e.clientX-p.x,e.clientY-p.y)>6)p.moved=true;if(p.id==='turn_handle'&&state.sceneStateId==='cylinder_placed'){turnBy((e.clientX-p.lastX)*.02);p.lastX=e.clientX;return;}const canDrag=(state.sceneStateId==='place_cylinder'&&p.id==='cylinder')||(state.sceneStateId==='compare_move'&&p.id==='cuboid');if(!canDrag||!p.moved)return;state.selectedMeshId=p.id;ray(e);raycaster.ray.intersectPlane(ground,hit);meshes[p.id].position.x=Math.max(-5,Math.min(5,hit.x));meshes[p.id].position.z=Math.max(-2.5,Math.min(3.5,hit.z));snapshot();});
 $('world').addEventListener('pointerup',e=>{if(!pointer)return;const p=pointer;pointer=null;if(!p.moved){if(p.id==='turn_handle')turnBy(Math.PI/4);else select(p.id);return;}if(p.id==='turn_handle')return;const m=meshes[p.id];const canDrop=(state.sceneStateId==='place_cylinder'&&p.id==='cylinder')||(state.sceneStateId==='compare_move'&&p.id==='cuboid');if(canDrop){if(Math.abs(m.position.x-mat.position.x)<1.15&&Math.abs(m.position.z-mat.position.z)<.85){m.position.x=mat.position.x;m.position.z=mat.position.z;placeDone(p.id);}else{m.position.copy(p.start);cue(state.sceneStateId==='place_cylinder'?'ug_3d_place_miss':'ug_3d_compare_ok');snapshot();}}else select(p.id);});
 $('world').addEventListener('pointercancel',()=>{if(pointer?.id!=='turn_handle'&&pointer&&meshes[pointer.id])meshes[pointer.id].position.copy(pointer.start);pointer=null;snapshot();});
 $('world').addEventListener('keydown',e=>{if(e.key==='ArrowRight'&&state.sceneStateId==='cylinder_placed'){e.preventDefault();turnBy(Math.PI/4);}if(e.key==='Enter')moveToMat();});
 const observer=new ResizeObserver(()=>{const w=$('world').clientWidth,h=$('world').clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();});observer.observe($('world'));function frame(){requestAnimationFrame(frame);renderer.render(scene,camera);}ready=true;$('loading').hidden=true;reset(false);if(queuedTeacherState){applyTeacherState(queuedTeacherState);queuedTeacherState=null;}frame();
}catch(_){$('loading').textContent='再试一次';$('loading').onclick=()=>location.reload();cue('ug_3d_load_retry');}
""".replace("ART_JSON", json.dumps({s:svg(s,True) for s in ("sphere","cylinder","cuboid")},ensure_ascii=False))
    vendored=REPO/'openmaic-runtime/.runtime/OpenMAIC/public/vendor/three/0.160.0/three.module.js'
    module_bytes=vendored.read_bytes()
    if hashlib.sha256(module_bytes).hexdigest()!='76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495':
        raise ValueError('pinned_three_dependency_changed')
    # The activity intentionally runs with an opaque sandbox origin. A self-
    # contained pinned module avoids cross-origin fetch without weakening it.
    data_uri='data:text/javascript;base64,'+base64.b64encode(module_bytes).decode('ascii')
    js=js.replace("await import('/vendor/three/0.160.0/three.module.js')",'await import('+json.dumps(data_uri)+')')
    return html_page("模型摆一摆", body, manifest, js, True)


def recap_html(design):
    manifest, js = cue_bundle(design, "ug_solids_recap")
    pictures = ''.join('<button class="picture" data-mira-picture-choice="'+s+'" data-shape="'+s+'" aria-label="观察桌面物品">'+svg(s,True,True)+'</button>' for s in ('sphere','cube','cylinder','cuboid'))
    # Original pictorial previews orient the directory; they do not invent or
    # stand in for the still unreviewed lesson objectives.
    panels = [svg('cube')+svg('sphere'), '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><path d="M20 85H180M30 85V50H70V85M80 85V30H120V85M130 85V50H170V85" fill="#d1a875" stroke="#6c6257" stroke-width="3"/><path d="M70 50L100 15L130 50" fill="#95b7af" stroke="#6c6257" stroke-width="3"/></svg>', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><rect x="40" y="55" width="120" height="30" rx="2" fill="#ba8b61" stroke="#69533d" stroke-width="3"/><rect x="60" y="25" width="80" height="30" fill="#91afa6" stroke="#4e746a" stroke-width="3"/><path d="M50 85V95M150 85V95" stroke="#69533d" stroke-width="5"/></svg>']
    nodes=design['directoryNodes']
    # Nodes can contain supplemental source evidence; only explicit IDs/titles
    # are placed in the student map.
    mapping=''.join('<button id="node'+str(i+1)+'" data-mira-node-id="'+n['nodeId']+'" aria-label="'+n['title']+'">'+panels[i]+'<span>'+n['title']+'</span></button>' for i,n in enumerate(nodes))
    body='<div class="tools"><button id="replay" aria-label="再听一次">'+REPLAY+' 再听</button><button id="finish">发现了</button></div><p id="note" class="note" aria-live="polite"></p><section class="board"><div class="life-grid">'+pictures+'</div></section><nav class="map" aria-label="本单元接下来一起探索">'+mapping+'</nav>'
    js+=r"""
const state={sceneStateId:'observe_life',observedShapeIds:[],visitedNodeIds:[],finished:false};function emit(){document.documentElement.dataset.miraState=JSON.stringify(state);parent.postMessage({type:'MIRA_WIDGET_STATE',state:{...state}},'*');}
document.querySelectorAll('[data-shape]').forEach(b=>b.onclick=()=>{const shape=b.dataset.shape;if(!state.observedShapeIds.includes(shape))state.observedShapeIds.push(shape);b.classList.add('selected');playCue('ug_recap_'+shape);emit();});
for(let i=1;i<=3;i++){const b=document.getElementById('node'+i);b.onclick=()=>{state.visitedNodeIds.push(b.dataset.miraNodeId);playCue('ug_recap_lesson'+i);emit();};}
document.getElementById('replay').onclick=()=>playCue(currentCue);document.getElementById('finish').onclick=()=>{state.finished=true;state.sceneStateId='finished';playCue('ug_recap_end');emit();};
window.addEventListener('message',event=>{if(event.source!==parent)return;const data=event.data;if(!data||typeof data.type!=='string')return;if(data.type==='SET_WIDGET_STATE'&&data.state?.sceneStateId==='observe_life'){state.sceneStateId='observe_life';state.finished=false;emit();}else if(data.type==='HIGHLIGHT_ELEMENT'&&typeof data.target==='string'){highlightTarget(data.target);}});
showCue('ug_recap_enter');emit();
"""
    return html_page("生活里找一找", body, manifest, js)


def speech(scene, text, suffix="enter"):
    return {"id":scene+"_"+suffix,"type":"speech","text":text,"agentId":"mira-textbook-e43307857c3c-default-1"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=SOURCE/'derived-local-solids-v1'/TASK)
    args=parser.parse_args()
    output=args.output.resolve()
    if SOURCE.resolve() not in output.parents or not any(p.startswith('derived-') for p in output.relative_to(SOURCE).parts):
        raise SystemExit('output must be an owned new derived-* directory')
    if output.exists():
        raise SystemExit('refusing to replace an existing derived candidate')
    design=json.loads(DESIGN.read_text());source_input=json.loads((SOURCE/'input.json').read_text())
    raw1=json.loads((RAW/'0005-scene-1-content.json').read_text())['value']['content']
    original_paths=[SOURCE/'input.json',SOURCE/'state.json',DESIGN,*sorted(RAW.glob('*.json'))]
    before={str(p.relative_to(REPO)):sha_file(p) for p in original_paths}
    if not VIDEO.is_file() or sha_file(VIDEO)!=VIDEO_SHA or b'ftyp' not in VIDEO.read_bytes()[:40]:
        raise SystemExit('real reviewed source MP4 hash does not match')
    now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z');ms=int(datetime.now(timezone.utc).timestamp()*1000)
    teacher=design['teacherContract'];native_teacher=teacher['runtime']
    agents=[{'id':'mira-textbook-e43307857c3c-default-1','name':'小数老师','role':'teacher','persona':'你是小数老师。用图片、简短口语和鼓励引导一年级儿童观察、尝试和表达，不把提示后的表现称为独立掌握。','avatar':native_teacher['avatar'],'color':'#3b82f6','priority':10,'teacherProfile':{k:teacher['teacherProfile'][k] for k in ('id','version','contentHash')},'voiceConfig':native_teacher['voiceConfig']}]
    # Preserve actual native peer names/personalities instead of inventing a
    # different discussion roster. Identities are isolated from global defaults.
    roster_source=REPO/'openmaic-runtime/.runtime/OpenMAIC/lib/orchestration/registry/store.ts'
    roster_text=roster_source.read_text()
    for i in range(2,7):
        block=re.search(r"'default-"+str(i)+r"': \{(.*?)\n  \},",roster_text,re.S)
        if block is None:raise SystemExit('native peer roster changed')
        block=block.group(1)
        get=lambda key:re.search(r'\b'+key+r": '([^']*)'",block).group(1)
        persona=re.search(r'persona: `(.*?)`',block,re.S).group(1)
        agents.append({'id':f'mira-textbook-e43307857c3c-default-{i}','name':get('name'),'role':get('role'),'persona':persona,'avatar':get('avatar'),'color':get('color'),'priority':int(re.search(r'priority: (\d+)',block).group(1))})
    stage={'id':CLASSROOM,'name':'认识立体图形 · 一起发现','style':'interactive','createdAt':ms,'updatedAt':ms,'languageDirective':'使用简体中文和小数老师预录普通话。面向一年级上册儿童，以可分辨的图片和观察操作为主，文字辅助。','generatedAgentConfigs':agents,'videoManifest':{}}
    # Preserve the generated slide title and observation instruction. Replace
    # its fake play-triangle/grey rectangle with the actual persisted MP4.
    canvas={'id':'solids_observation_canvas','viewportSize':1000,'viewportRatio':0.5625,
            'theme':{'backgroundColor':'#ffffff','themeColors':['#5b9bd5','#ed7d31','#a5a5a5','#ffc000','#4472c4'],'fontColor':'#333333','fontName':'Microsoft YaHei','outline':{'color':'#d14424','width':2,'style':'solid'},'shadow':{'h':0,'v':0,'blur':10,'color':'#000000'}},
            'elements':deepcopy(raw1['elements']),'background':deepcopy(raw1['background'])} if 'elements' in raw1 else None
    if canvas is None:
        raise SystemExit('unexpected source slide content shape')
    texts=[deepcopy(e) for e in canvas['elements'] if e.get('type')=='text' and e.get('id') in ('text_tLO7Cgm8','text_y5-HZpo8')]
    if len(texts)!=2:
        raise SystemExit('source observation title/instruction anchors changed')
    texts[0].update(left=60,top=22,width=880,height=54)
    texts[1].update(left=60,top=80,width=880,height=40)
    texts.append({'id':'solids_life_video','type':'video','left':180,'top':136,'width':640,'height':360,'rotate':0,'src':f'/api/classroom-media/{CLASSROOM}/media/solids-desk-observation-v1.mp4','autoplay':False,'ext':'mp4'})
    canvas.update(id='solids_observation_canvas',elements=texts)
    titles=['找形状朋友','形状朋友回家','模型摆一摆','生活里找一找']
    ids=['ug_solids_video','ug_solids_game','ug_solids_3d','ug_solids_recap']
    scenes=[]
    scene1={'id':ids[0],'outlineId':'outline_solids_0','stageId':CLASSROOM,'type':'slide','title':titles[0],'order':0,'content':{'type':'slide','canvas':canvas},'actions':[speech(ids[0],'看看这段动画，找找桌上的东西是什么样子。'),{'id':'ug_solids_video_play','type':'play_video','elementId':'solids_life_video'},speech(ids[0],'看完了，给这些东西找形状朋友。','after')],'createdAt':ms,'updatedAt':ms}
    scenes.append(scene1)
    for i,(html,widget,cue) in enumerate([(game_html(design),'game','找一找，哪个东西像球？'),(three_html(design),'visualization3d','看看玩具球，点出样子像它的模型。'),(recap_html(design),'simulation','看看这张新桌面，点一件你想观察的东西。')],1):
        scenes.append({'id':ids[i],'outlineId':f'outline_solids_{i}','stageId':CLASSROOM,'type':'interactive','title':titles[i],'order':i,'content':{'type':'interactive','url':'','html':html,'widgetType':widget,'widgetConfig':{'title':titles[i]}},'actions':[speech(ids[i],cue)],'createdAt':ms,'updatedAt':ms})
    classroom={'id':CLASSROOM,'createdAt':now,'stage':stage,'scenes':scenes}
    workload=narration_workload(classroom)
    actual_cues={c['cueId'] for c in workload if c['kind']=='interactive'}
    inventory=[{**c,'originalCueId':c['cueId'],'cueId':c['cueId'].replace('.','_')} for c in design['finiteCues'] if c['cueId'].replace('.','_') in actual_cues]
    actual_text={c['cueId']:c['text'] for c in workload if c['kind']=='interactive'}
    for cue in inventory:
        if cue['teacherText']!=actual_text[cue['cueId']]:
            cue['originalTeacherText']=cue['teacherText'];cue['teacherText']=actual_text[cue['cueId']]
            cue['textSha256']=hashlib.sha256(cue['teacherText'].encode()).hexdigest()
            cue['changeReason']='Describe performed actions without capability/mastery inference.'
    # These structural checks are deliberately not a teaching or runtime pass.
    for scene in scenes[1:]:
        html=scene['content']['html'];interactive_cues(html)
        if re.search(r'speechSynthesis|SpeechSynthesisUtterance|\.action\b|\.payload\b',html):
            raise SystemExit('forbidden speech or legacy protocol remains')
        if re.search(r"window\.miraNarrate\(\s*[^'\"]",html):
            raise SystemExit('nonliteral cue dispatch remains')
    if [sha_file(p) for p in original_paths]!=list(before.values()):
        raise SystemExit('source content changed during authoring')
    output.mkdir(parents=True)
    shutil.copyfile(SOURCE/'input.json',output/'input.json')
    (output/'media').mkdir();shutil.copyfile(VIDEO,output/'media'/VIDEO.name)
    save(output/'classroom.json',classroom);save(output/'finite-cue-inventory.json',{'schemaVersion':'mira.local-candidate.finite-cues.v1','status':'audio_not_generated','publicationAllowed':False,'cues':inventory,'runtimeNarrationSegmentCount':len(workload)})
    state={'schemaVersion':'mira.textbook.private-batch-generation-state.v1','taskId':TASK,'status':'generated_needs_review','authoringMode':'local_original_derivation','sourceGenerationJobId':'7Gmq77OFlk','sourceGenerationStatus':'failed','parentInputSha256':before[str((SOURCE/'input.json').relative_to(REPO))],'inputSha256':digest(source_input),'classroomId':CLASSROOM,'classroomSha256':digest(classroom),'runtimeOrigin':'http://127.0.0.1:3100','providerDispatched':False,'publicationAllowed':False,'studentDeliveryAllowed':False,'createdAt':ms,'updatedAt':ms}
    save(output/'state.json',state)
    record={'schemaVersion':'mira.textbook.local-derivation-repair.v1','status':'draft_needs_runtime_and_semantic_review','classroomId':CLASSROOM,'taskId':TASK,'binding':design['binding'],'manifestSha256':design['manifestSha256'],'publicationAllowed':False,'studentDeliveryAllowed':False,'providerCalls':0,'ttsCalls':0,'asrCalls':0,'sourceByteSha256':before,'parentRawSha256':before[str((RAW/'0008-scene-2-content-raw.json').relative_to(REPO))],'classroomCanonicalSha256':digest(classroom),'classroomFileSha256':sha_file(output/'classroom.json'),'teacherContract':teacher,'repairs':[{'sceneId':ids[0],'change':'Retained original generated title/instruction; replaced decorative placeholder and fake triangle with actual original animation MP4; teacher introduction precedes blocking play_video and post-video bridge.'},{'sceneId':ids[1],'change':'Preserved original fixed-round picture-matching and storage-table concept; independently redrew valid perspective SVG objects and rebuilt unsafe event/cue logic. Fixed literal cues; static picture containers; correct feedback waits for a separate child Continue; neutral three-home choices; real drag/drop and keyboard/tap equivalent; wrong drop retries.'},{'sceneId':ids[2],'change':'New original Three.js geometry, raycasting, real mesh translation, torus handle rotation and quaternion-equivalent Euler object orientation. Finite select/place/turn/compare/move states. No CSS fake 3D; no camera-only completion.'},{'sceneId':ids[3],'change':'New pictorial life transfer observation and exact three manifest node IDs/titles, with independently drawn preview illustrations. No quizzes, scores or mastery grant.'}],'finiteCueMapping':{c['originalCueId']:c['cueId'] for c in inventory},'video':{'path':str(VIDEO.relative_to(REPO)),'localCopy':f'media/{VIDEO.name}','sourceSha256':VIDEO_SHA,'src':texts[-1]['src'],'kind':'original_animation','durationSeconds':12,'deliveryCopiedToRuntime':False,'runtimePlaybackVerified':False},'remainingReview':['Native runtime registration and real MP4 fetch/play/pause/replay must be verified.','Local Three.js module /vendor/three/0.160.0/three.module.js must be verified; no new provider or paid media calls are performed.','All branches need real Qwen teacher audio and ASR before child delivery.','Inspect actual sphere/cube/cylinder/cuboid pictures and every incorrect/retry/drag/turn/comparison branch in the browser.','Directory binding is verified; source lesson briefs/knowledge remain pending teaching review. This preview does not certify complete textbook lesson alignment.','No review approval, publication or student course attachment has occurred.'],'runtimeNarrationSegmentCount':len(workload),'originalDesignCueCount':len(inventory),'sourceUnchangedAfterWrite':all(sha_file(p)==before[str(p.relative_to(REPO))] for p in original_paths)}
    save(output/'repair-record.json',record)
    print(json.dumps({'output':str(output),'classroomId':CLASSROOM,'classroomSha256':digest(classroom),'sceneCount':4,'narrationSegments':len(workload),'sourceUnchanged':record['sourceUnchangedAfterWrite']},ensure_ascii=False))


if __name__=='__main__':
    main()

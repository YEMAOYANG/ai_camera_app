"""Original illustrated reading and rhythm activities for early primary grades.

Recipes contain reviewed teaching text and finite cues, never executable code.
Rhythm practice counts voluntary taps; it does not assess reading or musical skill.
"""
from html import escape

from content import textbook_activity_templates as t


def child(x, y, color='#7b9dba', scale=1, speaking=False):
    mouth = 'M84 94q8 12 16 0' if speaking else 'M85 95q7 5 14 0'
    return (f'<g transform="translate({x} {y}) scale({scale})">'
            '<path d="M61 173v-50q31-23 62 0v50" fill="'+color+'"/>'
            '<ellipse cx="92" cy="75" rx="28" ry="33" fill="#e7bb96"/>'
            '<path d="M65 73V50q25-28 53 0v23l-20-18-16 13Z" fill="#594839"/>'
            '<circle cx="84" cy="77" r="3" fill="#3c3932"/><circle cx="102" cy="77" r="3" fill="#3c3932"/>'
            '<path d="'+mouth+'" fill="none" stroke="#9c624e" stroke-width="3"/>'
            '<path d="M69 132 53 151m62-19 16 19" stroke="#e7bb96" stroke-width="12" stroke-linecap="round"/>'
            '</g>')


def picture(key):
    bg = '<rect width="320" height="220" rx="18" fill="#eef3dc"/><path d="M0 162Q160 139 320 158V220H0Z" fill="#b9cda1"/>'
    book = '<path d="M101 142q29-12 59 0 31-12 59 0v43q-29-12-59 0-31-12-59 0Z" fill="#fff0c9" stroke="#967a55" stroke-width="4"/><path d="M160 142v43" stroke="#967a55" stroke-width="3"/>'
    if key == 'boat':
        art = bg + '<path d="M0 154h320v66H0Z" fill="#a5d5d8"/><path d="M29 156q47-88 98 0" fill="none" stroke="#ae9875" stroke-width="15"/><path d="M22 152h112" stroke="#ae9875" stroke-width="6"/><g id="moving"><path d="m154 161 38 26h76l31-26Z" fill="#c19268" stroke="#8d694d" stroke-width="3"/><path d="M221 158V71l-56 84Z" fill="#fff2c8" stroke="#b79a70" stroke-width="3"/><path d="M228 150V82l42 68Z" fill="#e5bd78"/></g><path d="M143 198q18-7 36 0m49 0q21-7 42 0" fill="none" stroke="#e8f6ed" stroke-width="4"/>'
        label = '小纸船在水面上，前面有一座小桥'
    elif key == 'rabbit':
        art = bg + '<g id="moving"><ellipse cx="161" cy="162" rx="47" ry="32" fill="#fff9e8" stroke="#b3aa91" stroke-width="3"/><ellipse cx="186" cy="117" rx="32" ry="34" fill="#fff9e8" stroke="#b3aa91" stroke-width="3"/><ellipse cx="173" cy="68" rx="10" ry="35" fill="#fff9e8" stroke="#b3aa91" stroke-width="3"/><ellipse cx="198" cy="65" rx="11" ry="38" fill="#fff9e8" stroke="#b3aa91" stroke-width="3"/><path d="M172 52v31m25-39v35" stroke="#e9baa4" stroke-width="6"/><circle cx="199" cy="113" r="4" fill="#524b3d"/><ellipse cx="216" cy="130" rx="5" ry="3" fill="#c3897a"/><circle cx="114" cy="152" r="13" fill="#fff9e8"/><ellipse cx="174" cy="188" rx="29" ry="9" fill="#eee7d4"/></g><path d="M42 184 29 151m13 33 17-45m-17 45 28-9" fill="none" stroke="#6c925e" stroke-width="5"/>'
        label = '长耳朵小白兔在草地上轻轻跳'
    elif key in {'share', 'aloud', 'together'}:
        art = bg + child(-13, 11, speaking=True) + child(136, 11, '#b99a75', speaking=False)
        if key == 'share':
            art += '<g id="moving">'+book+'</g><path d="M84 132 111 144m125-12-30 12" stroke="#e7bb96" stroke-width="11" stroke-linecap="round"/><path d="M89 44q22-24 43 0" fill="none" stroke="#77908a" stroke-width="4"/>'
            label = '两个朋友面向对方，微笑着交换一本儿歌书'
        elif key == 'aloud':
            art += '<g id="moving">'+book+'</g><path d="M226 133 219 123m16 12 8-14" stroke="#e7bb96" stroke-width="13" stroke-linecap="round"/><path d="M212 110 204 101m46 9 8-9" stroke="#bd9254" stroke-width="4"/>'
            label = '蓝衣朋友张嘴读书，棕衣朋友面向他轻轻鼓掌'
        else:
            art += '<g id="moving">'+book+'</g><path d="M91 126 119 150m115-24-33 24" stroke="#e7bb96" stroke-width="11" stroke-linecap="round"/>'
            label = '两个朋友坐在同一本打开的书旁边，一起听读'
    elif key == 'grab':
        art = bg + child(-13, 11) + child(136, 11, '#b99a75') + book + '<path d="M85 132 125 154m110-22-40 22" stroke="#e7bb96" stroke-width="13" stroke-linecap="round"/><path d="M141 118 155 105m13 12 13-16" stroke="#a87453" stroke-width="4"/><path d="M68 101h23m128 0h23" stroke="#935c4b" stroke-width="3"/>'
        label = '两个人都抓住书的一边，互相拉扯，书页卷起来了'
    else:
        raise ValueError('unsupported_original_reading_picture')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220" role="img" aria-label="'+escape(label, quote=True)+'"><title>'+label+'</title>'+art+'</svg>'


def reading_scene(scene, assets):
    body = '<div class="reading-pages">'
    for i, page in enumerate(scene['pages']):
        body += '<section data-reading-page="'+str(i)+'"'+(' hidden' if i else '')+'>'
        body += t.picture_button('page-'+str(i), page['assetId'], assets[page['assetId']], extra='data-reading-picture')
        body += '<p class="reading-verse">'+escape(page['displayText']).replace('\n', '<br>')+'</p></section>'
    body += '</div><div class="tools">'+t.button('start','听老师读','start','data-cancel')+t.button('replay','再听一遍','replay','data-cancel')+t.button('reset','从头再读','reset','data-cancel')+t.button('next','下一幅','next')+'</div>'
    body += '<style>.reading-pages{max-width:680px;margin:auto;text-align:center}.reading-pages button{width:100%;max-width:420px;padding:0}.reading-pages svg{display:block;width:100%;height:clamp(145px,29vh,230px)}.reading-verse{font-size:clamp(20px,3vw,30px);line-height:1.6;margin:8px 0;white-space:normal}@media(max-height:440px){.reading-pages svg{height:135px}.reading-verse{font-size:20px;margin:4px}}</style>'
    code = r'''
const reading=CONFIG;let pageIndex=0,heard=false,finished=false;
function refreshControls(){document.getElementById('next').disabled=interactionBusy||!heard||finished;}
function showPage(){document.querySelectorAll('[data-reading-page]').forEach((p,i)=>p.hidden=i!==pageIndex);heard=false;finished=false;refreshControls();}
function readPage(intro=false){run(async signal=>{if(intro)await narrate(reading.intro,signal);await narrate(reading.pages[pageIndex].cueId,signal);heard=true;});}
listen('start',()=>readPage(true));listen('replay',()=>readPage(false));listen('reset',()=>{cancelOperation();pageIndex=0;showPage();readPage(true);});
reading.pages.forEach((p,i)=>listen('page-'+i,()=>readPage(false)));
listen('next',()=>{if(interactionBusy||!heard||finished)return;if(pageIndex<reading.pages.length-1){pageIndex++;showPage();readPage();}else{run(async signal=>{await narrate(reading.complete,signal);finished=true;note.textContent='可以和家人一起再读一遍。';});}});
function applyTeacherState(state){if(Object.keys(state).length!==1||!Number.isInteger(state.pageIndex)||state.pageIndex<0||state.pageIndex>=reading.pages.length)return;assisted=true;cancelOperation();pageIndex=state.pageIndex;showPage();readPage();}
showPage();
'''.replace('CONFIG', t.js({'pages':scene['pages'],'intro':scene['initialCueId'],'complete':scene['completeCueId']}))
    return t.scene_html(scene, body, code)


def recitation_scene(scene, assets):
    """Picture-led voluntary recall, with an explicit model-reading reveal.

    Advancing records no mastery. A child may try aloud, think quietly, or ask
    for the model; the app does not infer recall from a tap or a narration end.
    """
    return _picture_recall_scene(scene, assets,
        prompt_label='听提示，试着背', model_label='听范读，看文字',
        complete_note='可以和家人一起，再试着背一背。')


def original_recall_scene(scene, assets):
    """Original pictured questions: try before optionally revealing a model."""
    return _picture_recall_scene(scene, assets,
        prompt_label='听问题，自己试', model_label='听老师示范',
        complete_note='可以回到前面再练，也可以讲给家人听。')


def _picture_recall_scene(scene, assets, *, prompt_label, model_label, complete_note):
    body = '<div class="recall-pages">'
    for i, page in enumerate(scene['pages']):
        body += '<section data-recall-page="'+str(i)+'"'+(' hidden' if i else '')+'>'
        body += t.picture_button('page-'+str(i),page['assetId'],assets[page['assetId']])
        body += '<p data-model-text hidden>'+escape(page['modelText']).replace('\n','<br>')+'</p></section>'
    body += '</div><div class="tools">'
    for identity,label,icon,extra in [('start',prompt_label,'start','data-cancel'),('model',model_label,'speaker',''),('reset','从头试一试','reset','data-cancel'),('next','下一幅','next','')]:
        body += t.button(identity,label,icon,extra)
    body += '</div><style>.recall-pages{max-width:680px;margin:auto;text-align:center}.recall-pages button{width:100%;max-width:420px;padding:0}.recall-pages svg{display:block;width:100%;height:clamp(145px,29vh,230px)}[data-model-text]{font-size:clamp(24px,3vw,32px);line-height:1.6;margin:8px 0}</style>'
    code = r'''
const recall=CONFIG;let recallIndex=0,promptReady=false,recallFinished=false;
function refreshControls(){for(const id of ['model','next'])document.getElementById(id).disabled=interactionBusy||!promptReady||recallFinished;}
function showRecall(){document.querySelectorAll('[data-recall-page]').forEach((p,i)=>p.hidden=i!==recallIndex);document.querySelectorAll('[data-model-text]').forEach(p=>p.hidden=true);promptReady=false;recallFinished=false;note.textContent='';refreshControls();}
function promptRecall(intro=false){promptReady=false;recallFinished=false;note.textContent='';document.querySelectorAll('[data-model-text]').forEach(p=>p.hidden=true);run(async signal=>{if(intro)await narrate(recall.intro,signal);await narrate(recall.pages[recallIndex].promptCueId,signal);promptReady=true;});}
listen('start',()=>promptRecall(true));listen('reset',()=>{cancelOperation();recallIndex=0;showRecall();promptRecall(true);});
recall.pages.forEach((p,i)=>listen('page-'+i,()=>promptRecall()));
listen('model',()=>{if(interactionBusy||!promptReady||recallFinished)return;document.querySelectorAll('[data-model-text]')[recallIndex].hidden=false;promptReady=false;run(async signal=>{await narrate(recall.pages[recallIndex].modelCueId,signal);promptReady=true;});});
listen('next',()=>{if(interactionBusy||!promptReady||recallFinished)return;if(recallIndex<recall.pages.length-1){recallIndex++;showRecall();promptRecall();}else{promptReady=false;run(async signal=>{await narrate(recall.complete,signal);recallFinished=true;note.textContent=recall.completeNote;});}});
function applyTeacherState(state){if(Object.keys(state).length!==1||!Number.isInteger(state.pageIndex)||state.pageIndex<0||state.pageIndex>=recall.pages.length)return;assisted=true;cancelOperation();recallIndex=state.pageIndex;showRecall();promptRecall();}
showRecall();
'''.replace('CONFIG',t.js({'pages':scene['pages'],'intro':scene['initialCueId'],'complete':scene['completeCueId'],'completeNote':complete_note}))
    return t.scene_html(scene,body,code)


DRUM = r'''
let pulseUntil=0;
function createScene(){meshes.length=0;part('ground','box',0,-.11,0,4.8,.12,2.8,[.78,.83,.71]);part('drum','cylinder',0,.75,0,1.8,1.3,1.8,[.72,.43,.28]);part('drum','cylinder',0,1.42,0,1.9,.12,1.9,[.94,.87,.65]);part('drum','cylinder',0,.12,0,1.9,.12,1.9,[.78,.68,.46]);for(let i=0;i<8;i++){const a=i*Math.PI/4;part('drum','box',.92*Math.cos(a),.75,.92*Math.sin(a),.065,1.12,.065,[.88,.75,.48]);}const struck=performance.now()<pulseUntil;part('drum','cylinder',.18,struck?1.70:2.12,.20,.10,.72,.10,[.48,.35,.23],0,struck?0:.7);part('drum','sphere',.18,struck?1.51:1.84,.20,.22,.22,.22,[.84,.76,.56]);if(struck)part('drum','cylinder',0,1.51,0,1.35,.018,1.35,[.72,.86,.72]);}
'''


RHYTHM = r'''
const rhythm=CONFIG;let rhythmIndex=0,taps=0,ready=false,complete=false,audioContext=null;
function refreshControls(){document.getElementById('tap').disabled=interactionBusy||!ready||complete||!gl;document.getElementById('next').disabled=interactionBusy||!complete;}
function refreshBeats(){const row=document.getElementById('beats');row.replaceChildren();for(let i=0;i<rhythm.patterns[rhythmIndex].beats;i++){const dot=document.createElement('i');dot.className=i<taps?'done':'';dot.setAttribute('aria-label',i<taps?'这一拍已敲':'这一拍还没敲');row.appendChild(dot);}document.querySelectorAll('[data-rhythm]').forEach((b,i)=>b.classList.toggle('selected',i===rhythmIndex));refreshControls();}
function sound(){pulseUntil=performance.now()+160;if(!audioContext)audioContext=new AudioContext();audioContext.resume();const osc=audioContext.createOscillator(),gain=audioContext.createGain(),now=audioContext.currentTime;osc.type='sine';osc.frequency.setValueAtTime(140,now);osc.frequency.exponentialRampToValueAtTime(65,now+.14);gain.gain.setValueAtTime(.22,now);gain.gain.exponentialRampToValueAtTime(.001,now+.18);osc.connect(gain);gain.connect(audioContext.destination);osc.start(now);osc.stop(now+.2);}
function pauseBeat(signal){return new Promise((resolve,reject)=>{let timer;const abort=()=>{clearTimeout(timer);reject(new Error('cancelled'));};signal.addEventListener('abort',abort,{once:true});timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},650);});}
function begin(index,intro=false){cancelOperation();rhythmIndex=index;taps=0;ready=false;complete=false;refreshBeats();run(async signal=>{if(!gl){await narrate(rhythm.retry,signal);return;}if(intro)await narrate(rhythm.intro,signal);await narrate(rhythm.patterns[index].cueId,signal);for(let i=0;i<rhythm.patterns[index].beats;i++){if(signal.aborted)throw new Error('cancelled');sound();taps=i+1;refreshBeats();await pauseBeat(signal);}taps=0;refreshBeats();await narrate(rhythm.yourTurn,signal);ready=true;});}
rhythm.patterns.forEach((p,i)=>listen('rhythm-'+i,()=>{if(!interactionBusy)begin(i);}));
listen('start',()=>begin(rhythmIndex,true));listen('replay',()=>begin(rhythmIndex));listen('reset',()=>{poses.drum.angle=0;begin(0,true);});
listen('tap',()=>{if(interactionBusy||!ready||complete||!gl)return;sound();taps++;refreshBeats();if(taps===rhythm.patterns[rhythmIndex].beats){ready=false;run(async signal=>{await narrate(rhythm.patterns[rhythmIndex].feedbackCueId,signal);complete=true;});}});
listen('next',()=>{if(interactionBusy||!complete)return;if(rhythmIndex<rhythm.patterns.length-1)begin(rhythmIndex+1);else run(signal=>narrate(rhythm.complete,signal));});
listen('rotate',()=>{if(interactionBusy||!gl)return;poses.drum.angle+=Math.PI/6;drawModel();});listen('model-retry',()=>{initModel();refreshControls();});
function applyTeacherState(state){if(Object.keys(state).length!==1||!Number.isInteger(state.rhythmIndex)||state.rhythmIndex<0||state.rhythmIndex>=rhythm.patterns.length)return;assisted=true;begin(state.rhythmIndex);}
initModel();refreshBeats();
'''


def rhythm_scene(scene, assets):
    body = '<canvas id="model-canvas" class="model" aria-label="可以转动和敲击的立体鼓"></canvas><div class="choices rhythm-choices">'+''.join(
        t.picture_button('rhythm-'+str(i),p['assetId'],assets[p['assetId']],extra='data-rhythm="'+str(i)+'"') for i,p in enumerate(scene['patterns']))+'</div><div id="beats" class="progress" aria-live="polite" aria-label="跟敲的拍数"></div><div class="tools">'
    for identity,label,icon,extra in [('start','先听老师说','start','data-cancel'),('replay','再听鼓点','replay','data-cancel'),('tap','跟着敲鼓','speaker',''),('rotate','转一转鼓','rotate',''),('reset','从头开始','reset','data-cancel'),('next','下一小节','next',''),('model-retry','重新加载鼓','replay','data-cancel hidden')]:
        body += t.button(identity,label,icon,extra)
    body += '</div><style>.rhythm-choices{max-width:480px;gap:8px;margin:6px auto}.rhythm-choices>button{min-height:65px;padding:3px}.rhythm-choices>button svg{max-height:58px}.model{height:clamp(130px,26vh,220px)}#tap{background:#f0cc7a;border-color:#b78b42}#beats{margin:6px auto}#tap svg{width:36px;height:36px}</style>'
    # A drum face and visible beater are a more direct pictorial action than a speaker.
    body = body.replace(t.ICONS['speaker'], '<ellipse cx="32" cy="36" rx="24" ry="14" fill="#c88d5b"/><ellipse cx="32" cy="29" rx="24" ry="14" fill="#eed79a"/><path d="m28 8 9 22" stroke="#735640" stroke-width="6" stroke-linecap="round"/>', 1)
    engine = t.WEBGL
    old = "let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    if engine.count(old) != 1:
        raise ValueError('reading_drum_geometry_anchor_changed')
    engine = engine.replace(old,"const poses={drum:{x:0,z:0,angle:0}};")
    start,end=engine.index('function createScene(){'),engine.index('\nfunction compile(')
    engine=engine[:start]+DRUM+engine[end:]
    engine=engine.replace("if(gl&&!document.hidden)drawModel();","if(gl&&!document.hidden){createScene();drawModel();}")
    config = {'patterns':scene['patterns'],'intro':scene['initialCueId'],'retry':scene['retryCueId'],
              'yourTurn':scene['yourTurnCueId'],'complete':scene['completeCueId']}
    return t.scene_html(scene,body,engine+RHYTHM.replace('CONFIG',t.js(config)))

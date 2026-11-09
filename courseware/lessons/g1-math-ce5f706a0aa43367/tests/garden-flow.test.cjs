'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const path=require('node:path');const {execFileSync}=require('node:child_process');const root=path.resolve(__dirname,'../../../..');const {JSDOM,VirtualConsole}=require(require.resolve('jsdom',{paths:[path.join(root,'student-web')]}));
const keys=['p02','p04','p07','p09','p11','p13','p16','p17','p19','p22','p23'];
function open(key){
 const py="from pathlib import Path;import sys;from courseware.kit.page import page;s=Path('courseware/lessons/g1-math-ce5f706a0aa43367/pages');k=sys.argv[1];print(page(k,(s/(k+'.html')).read_text(),(s/(k+'.css')).read_text(),(s/(k+'.js')).read_text()))";
 const html=execFileSync('python3',['-B','-c',py,key],{cwd:root,encoding:'utf8'});let now=0,queue=[],seq=0,errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=new JSDOM(html,{runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){w.innerWidth=1280;w.innerHeight=720;w.setTimeout=(fn,ms=0)=>{const id=++seq;queue.push({id,at:now+ms,fn});return id;};w.clearTimeout=id=>{queue=queue.filter(t=>t.id!==id);};}});const w=dom.window,d=w.document;
 function advance(ms){const end=now+ms;let safety=0;while(true){queue.sort((a,b)=>a.at-b.at);if(!queue.length||queue[0].at>end)break;const t=queue.shift();now=t.at;t.fn();if(++safety>10000)throw Error('timer loop');}now=end;}
 function click(sel,i=0){const es=Array.from(d.querySelectorAll(sel));assert.ok(es[i],key+' missing '+sel+' #'+i);es[i].click();}
 return {dom,w,d,advance,click,errors,state:()=>JSON.parse(JSON.stringify(w.GardenDebug.state())),cfg:()=>w.GardenDebug.config};
}
for(const key of keys)test(key+' teacher demonstration, first miss, full completion and play again',()=>{
 const h=open(key);const {w,d,click,advance}=h;assert.deepEqual(h.errors,[]);w.K.begin();w.K.onState({phase:'demo'});assert.equal(h.state().demo,true);w.K.onState({phase:'show'});assert.equal(h.state().show,true);assert.equal(w.K.stars,0);w.K.onState({phase:'play'});assert.equal(h.state().demo,false);assert.equal(h.state().level,0);
 const controls=Array.from(d.querySelectorAll('#play button'));assert.equal(controls.every(b=>Boolean(b.id)),true);assert.equal(new Set(controls.map(b=>b.id)).size,controls.length);const cfg=h.cfg();let testedMiss=false;
 for(let level=0;level<cfg.levels.length;level++){
  const v=cfg.levels[level];assert.equal(h.state().level,level);
  if(cfg.mode==='count'){
   assert.equal(Array.from(d.querySelectorAll('.garden-count-option')).every(b=>b.disabled),true);click('#garden-choices button');assert.equal(h.state().misses,0);for(let i=0;i<v;i++)click('.garden-pot',i);if(!testedMiss){Array.from(d.querySelectorAll('.garden-count-option')).find(b=>b.getAttribute('aria-label')!=='选择'+v+'个数量点').click();assert.equal(h.state().misses,1);assert.equal(h.state().marked.length,v);assert.equal(w.K.stars,0);assert.equal(d.querySelector('.garden-demo-answer'),null);testedMiss=true;}Array.from(d.querySelectorAll('.garden-count-option')).find(b=>b.getAttribute('aria-label')==='选择'+v+'个数量点').click();
  }else if(['shape','print','fit'].includes(cfg.mode)){
   const target=typeof v==='string'?v:v.shape;const index=cfg.mode==='shape'?cfg.options.indexOf(target):cfg.mode==='print'?['square','circle','rectangle'].indexOf(target):2;
   if(!testedMiss){const bad=cfg.mode==='fit'?0:(index+1)%d.querySelectorAll('.garden-shape-option').length;click('.garden-shape-option',bad);click('#garden-drop');assert.equal(w.K.stars,0);assert.equal(h.state().misses,1);testedMiss=true;}
   click('.garden-shape-option',index);click('#garden-drop');
  }else if(['height','length'].includes(cfg.mode)){
   const sel=cfg.mode==='height'?'.garden-tower-wrap':'.garden-ribbon-wrap';if(cfg.mode==='length')click('#garden-choices button');click(sel,0);click(sel,1);assert.deepEqual(h.state().aligned,[true,true]);
   const correct=v[0]>v[1]?0:1;if(!testedMiss){click(sel,1-correct);assert.equal(h.state().misses,1);assert.equal(w.K.stars,0);testedMiss=true;}click(sel,correct);
  }else if(cfg.mode==='pair'){
   assert.equal(Array.from(d.querySelectorAll('.garden-row-choice')).every(b=>b.disabled),true);click('#garden-choices button',1);assert.equal(h.state().misses,0);for(let i=0;i<Math.min(...v);i++){click('.garden-dotrow.top button',i);click('.garden-dotrow.bottom button',i);}assert.equal(h.state().pairs.length,Math.min(...v));if(!testedMiss){click('#garden-choices button',1);assert.equal(h.state().misses,1);assert.equal(h.state().pairs.length,Math.min(...v));testedMiss=true;}click('#garden-choices button',v[0]===v[1]?1:v[0]>v[1]?0:2);
  }else if(cfg.mode==='size'){
   click('.garden-paper',1);assert.equal(h.state().overlay,true);assert.equal(Array.from(d.querySelectorAll('.garden-paper')).every(el=>el.disabled),true);const correct=v[0]>v[1]?0:1;if(!testedMiss){click('#garden-choices button',1-correct);assert.equal(h.state().misses,1);testedMiss=true;}click('#garden-choices button',correct);
  }else if(cfg.mode==='infer'){
   if(!testedMiss){assert.equal(d.querySelector('#garden-check-count').disabled,true);click('#garden-choices .garden-confirm');assert.equal(h.state().revealed,false);assert.equal(h.state().misses,0);}click('.garden-container.left');if(!testedMiss){click('#garden-check-count');assert.equal(h.state().misses,1);testedMiss=true;}const needed=v[0]-v[1];for(let i=0;i<needed;i++)click('#garden-choices button',0);assert.equal(h.state().guess,needed);click('#garden-choices .garden-confirm');
  }else if(cfg.mode==='sort'){
   const bins={book:'book',notebook:'notebook',pencil:'pencil-case'};
   for(let i=0;i<v.length;i++){d.querySelector('.garden-sort-item[data-index="'+i+'"]').click();if(!testedMiss){const bad=Array.from(d.querySelectorAll('.garden-bin')).find(b=>b.dataset.bin!==bins[v[i]]);bad.click();assert.equal(Object.keys(h.state().placed).length,0);assert.equal(h.state().misses,1);testedMiss=true;d.querySelector('.garden-sort-item[data-index="'+i+'"]').click();}d.querySelector('.garden-bin[data-bin="'+bins[v[i]]+'"]').click();}assert.equal(d.querySelectorAll('.garden-sort-item').length,0);assert.equal(d.querySelectorAll('.garden-stored img').length,v.length);
  }else if(cfg.mode==='books'){
   assert.equal(d.querySelector('#garden-check-order').disabled,true);if(!testedMiss){d.querySelector('#garden-book-100').click();click('.garden-book-slot',0);assert.equal(h.state().misses,1);assert.deepEqual(h.state().slots,[null,null,null]);testedMiss=true;}
   [190,145,100].forEach((size,i)=>{const b=d.querySelector('#garden-book-'+size);assert.ok(b);b.click();click('.garden-book-slot',i);});click('#garden-check-order');
  }
  advance(700);assert.equal(h.state().level,level+1);
 }
 assert.equal(w.K.stars,cfg.levels.length);assert.ok(d.querySelector('#finish:not(.gone)'));click('#btn-again');assert.equal(h.state().level,0);assert.equal(h.state().misses,0);assert.equal(w.K.stars,0);assert.equal(d.querySelector('#finish').classList.contains('gone'),true);assert.deepEqual(h.errors,[]);h.dom.window.close();
});

test('graded visual hints reveal an answer only on the third miss, then return the same level without awarding stars',()=>{const h=open('p07');h.w.K.begin();h.click('.garden-tower-wrap',0);h.click('.garden-tower-wrap',1);const wrong=h.cfg().levels[0][0]>h.cfg().levels[0][1]?1:0;for(let n=1;n<=3;n++){h.click('.garden-tower-wrap',wrong);assert.equal(h.state().level,0);assert.equal(h.w.K.stars,0);assert.equal(Boolean(h.d.querySelector('.garden-demo-answer')),n===3);}h.advance(1700);assert.equal(h.state().level,0);assert.equal(h.state().show,false);assert.equal(h.state().misses,0);assert.deepEqual(h.state().aligned,[false,false]);assert.equal(h.d.querySelector('.garden-demo-answer'),null);h.dom.window.close();});

test('inference controls keep identity while quantity chips appear or disappear',()=>{const h=open('p19');h.w.K.begin();h.d.querySelector('#garden-peek').click();h.d.querySelector('#garden-reserve-1').click();assert.equal(h.state().guess,1);assert.ok(h.d.querySelector('#garden-check-count'));h.d.querySelector('#garden-hidden-dot-1').click();assert.equal(h.state().guess,0);assert.ok(h.d.querySelector('#garden-reserve-1'));assert.ok(h.d.querySelector('#garden-check-count'));h.dom.window.close();});

test('the level reset remains available outside the answer operation area',()=>{const h=open('p19');assert.equal(h.d.querySelector('#garden-reset').parentElement.id,'cv');h.w.K.begin();h.d.querySelector('#garden-peek').click();h.d.querySelector('#garden-reset').click();assert.equal(h.state().revealed,false);assert.equal(h.state().level,0);h.dom.window.close();});

test('the printing demonstration changes its displayed outline before each corresponding line',()=>{
 const h=open('p16'),scene=require('../lesson.json').scenes.find(s=>s.key==='p16');const seen=[];h.w.K.begin();
 for(const beat of scene.script){if(beat.setState)h.w.K.onState(beat.setState);if(!beat.say)continue;const shape=h.d.querySelector('#garden-drop svg g > *');if(beat.say.startsWith('正方体的这个面')){assert.equal(shape.getAttribute('height'),'164');seen.push('square');}if(beat.say.startsWith('圆柱平平的底面')){assert.equal(shape.localName,'circle');seen.push('circle');}if(beat.say.startsWith('这里长方体选中的面')){assert.equal(shape.getAttribute('height'),'110');seen.push('rectangle');}}
 assert.deepEqual(seen,['square','circle','rectangle']);assert.equal(h.state().demo,false);assert.equal(h.w.K.stars,0);h.dom.window.close();
});

test('each narrated count marks one more pot and the live round starts clear',()=>{
 const h=open('p02'),scene=require('../lesson.json').scenes.find(s=>s.key==='p02');const seen=[];h.w.K.begin();
 for(const beat of scene.script){if(beat.setState)h.w.K.onState(beat.setState);if(beat.say&&/^第[一二三]盆/.test(beat.say))seen.push([h.d.querySelectorAll('.garden-pot.marked').length,h.d.querySelectorAll('.garden-count-line i').length,Boolean(h.d.querySelector('.garden-demo-answer'))]);}
 assert.deepEqual(seen,[[1,1,false],[2,2,false],[3,3,true]]);assert.equal(h.d.querySelectorAll('.garden-pot.marked').length,0);assert.equal(h.state().demo,false);assert.equal(h.w.K.stars,0);h.dom.window.close();
});

test('a failed print shows the attempted shape beside the prompt and allows the correct print',()=>{
 const h=open('p16');h.w.K.begin();h.click('.garden-shape-option',1);h.click('#garden-drop');assert.equal(h.state().misses,1);assert.equal(h.w.K.stars,0);assert.ok(h.d.querySelector('#garden-drop > svg rect'));assert.ok(h.d.querySelector('.garden-try-print circle'));h.click('.garden-shape-option',2);h.click('#garden-drop');assert.equal(h.d.querySelector('.garden-try-print'),null);assert.ok(h.d.querySelector('#garden-drop > svg rect'));assert.equal(h.w.K.stars,1);h.dom.window.close();
});

test('the two narrated inference examples show the corresponding total and known dots',()=>{
 const h=open('p19'),scene=require('../lesson.json').scenes.find(s=>s.key==='p19');const seen=[];h.w.K.begin();
 for(const beat of scene.script){if(beat.setState)h.w.K.onState(beat.setState);if(!beat.say||!beat.say.startsWith('总共'))continue;const counts=['.garden-total i','.garden-container.left i','.garden-container.right .garden-hidden-dot svg circle'].map(s=>h.d.querySelectorAll(s).length);seen.push(counts);}
 assert.deepEqual(seen,[[1,0,1],[2,1,1]]);assert.equal(h.state().demo,false);assert.equal(h.state().revealed,false);assert.equal(h.w.K.stars,0);h.dom.window.close();
});

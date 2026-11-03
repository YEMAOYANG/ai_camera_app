(function(){
K.hud({icon:'🛡️',title:'整理安全做法',levels:2});K.owl();
K.ready({emoji:'🧩',title:'整理安全做法',sub:'找身体，换动作',btn:'start-btn'});
var tray=K.$('#tray'),zones=K.$$('#zones button'),level=0,selected=null,misses=0,placed={},demoDone=false,busy=false;
var zoneName={eye:'eye',ear:'ear',nose:'nose',skin:'skin'};
var actions=[
 {id:'action-1',zone:'eye',safe:true,art:'book'},
 {id:'action-2',zone:'ear',safe:true,art:'headphones'},
 {id:'action-3',zone:'nose',safe:true,art:'nose'},
 {id:'action-4',zone:'skin',safe:true,art:'hand'}
];
function art(type){
 if(type==='rub')return '<svg viewBox="0 0 180 160"><circle cx="89" cy="75" r="52" fill="#FFE4CF"/><path d="M92 20Q85 72 67 98q-4 13 25 15 31-2 25-16-15-27-25-77Z" fill="#E9AE80" stroke="#6B4423" stroke-width="7"/><path d="M35 30 145 137M145 30 35 137" stroke="#E4572E" stroke-width="10"/></svg>';
 if(type==='stick')return '<svg viewBox="0 0 180 160"><path d="M101 57q-8-25-30-18-18 7-14 36-3 36 31 39 23 2 32-21" fill="#E9AE80" stroke="#6B4423" stroke-width="7"/><path d="m105 106 36-65" stroke="#fff" stroke-width="12"/><path d="m105 106 36-65" stroke="#6B4423" stroke-width="5"/><path d="M34 27 146 139M146 27 34 139" stroke="#E4572E" stroke-width="9"/></svg>';
 if(type==='pick')return '<svg viewBox="0 0 180 160"><circle cx="88" cy="74" r="52" fill="#FFE4CF"/><path d="M91 18Q84 70 66 97q-4 13 25 15 31-2 25-16-15-27-25-78Z" fill="#E9AE80" stroke="#6B4423" stroke-width="7"/><path d="M34 28 144 137M144 28 34 137" stroke="#E4572E" stroke-width="10"/></svg>';
 if(type==='touch')return '<svg viewBox="0 0 180 160"><path d="M55 48h70v17h12v64q0 10-11 10H54q-11 0-11-10V65h12Z" fill="#D7D0C5" stroke="#6B4423" stroke-width="7"/><path d="M30 32 148 142M148 32 30 142" stroke="#E4572E" stroke-width="10"/><path d="M90 6v31m-14-15h28" stroke="#F6A935" stroke-width="7"/></svg>';
 if(type==='book')return '<svg viewBox="0 0 180 160"><path d="M18 34q38-12 72 8v96q-34-20-72-8Zm144 0q-38-12-72 8v96q34-20 72-8Z" fill="#fff" stroke="#6B4423" stroke-width="7"/><path d="M37 55q22-6 39 4m-39 15q22-6 39 4m25-19q20-10 39-4m-39 23q20-10 39-4" stroke="#4C8DDB" stroke-width="5" stroke-linecap="round"/><circle cx="90" cy="23" r="11" fill="#F6A935"/></svg>';
 if(type==='headphones')return '<svg viewBox="0 0 180 160"><path d="M39 89V70a51 51 0 0 1 102 0v19" fill="none" stroke="#6B4423" stroke-width="13"/><rect x="26" y="78" width="37" height="58" rx="14" fill="#4C8DDB" stroke="#2F66AE" stroke-width="6"/><rect x="117" y="78" width="37" height="58" rx="14" fill="#4C8DDB" stroke="#2F66AE" stroke-width="6"/><path d="M67 105h46" stroke="#58B45C" stroke-width="9" stroke-linecap="round"/><path d="m90 89 15 16-15 16" fill="none" stroke="#58B45C" stroke-width="8"/></svg>';
 if(type==='nose')return '<svg viewBox="0 0 180 160"><circle cx="88" cy="78" r="59" fill="#FFE4CF"/><path d="M91 23Q83 77 63 101q-4 14 27 16 32-3 26-17-16-26-25-77Z" fill="#E9AE80" stroke="#6B4423" stroke-width="7"/><path d="M75 103q15 9 30 0" fill="none" stroke="#B95D45" stroke-width="6"/><path d="M35 32 143 136M143 32 35 136" stroke="#E4572E" stroke-width="9" opacity=".8"/></svg>';
 return '<svg viewBox="0 0 180 160"><path d="M47 102V58q0-13 12-13t12 13v27-45q0-13 12-13t12 13v45-35q0-13 12-13t12 13v48q0 37-32 42-29 3-43-23L26 91q-5-11 5-16 10-4 16 8Z" fill="#E9AE80" stroke="#6B4423" stroke-width="7"/><path d="M23 132q66 10 132-9" fill="none" stroke="#58B45C" stroke-width="8" stroke-linecap="round"/></svg>';
}
function render(){tray.innerHTML='';selected=null;actions.forEach(function(a){if(placed[a.id])return;var b=K.el('button','action',art(a.art),tray);b.id=a.id;b.dataset.zone=a.zone;b.dataset.safe=String(a.safe);b.dataset.art=a.art;b.setAttribute('aria-label','动作图卡');b.addEventListener('click',function(){choose(b)});K.drag(b,{enabled:function(){return K.started&&!busy},targets:function(){return zones},onTap:function(){choose(b)},onDrop:function(el,target){if(level===1){choose(el)}else if(target)place(el,target.dataset.zone)}})});}
function choose(el){if(busy)return;if(level===1){var safe={rub:'book',stick:'headphones',pick:'nose',touch:'hand'};el.innerHTML=art(safe[el.dataset.art]);el.dataset.safe='true';el.classList.add('placed');placed[el.id]=true;K.sfx.ok();K.star(1,el);K.say('不安全动作换好了','ok');if(!K.$$('.action:not(.placed)').length)finishLevel();return}K.$$('.action').forEach(function(x){x.classList.remove('selected')});selected=el;el.classList.add('selected');K.sfx.pick();K.say('把动作放到相应部位旁')}
function hint(){misses++;K.sfx.no();var msg=misses===1?'看看动作涉及身体哪里':misses===2?'再看动作会怎样保护这个部位':'老师示范一次，再轮到你';K.say(msg,'no');if(misses>=3){var card=K.$('#action-1');if(card){card.classList.add('teach-hl');setTimeout(function(){card.classList.remove('teach-hl')},1800)}misses=0}}
function place(el,zone){if(!el||busy)return;var valid=level===0?el.dataset.zone===zone:el.dataset.zone===zone&&el.dataset.safe==='true';if(!valid){el.classList.add('wrong');setTimeout(function(){el.classList.remove('wrong')},500);hint();return}misses=0;placed[el.id]=true;el.classList.add('placed');var target=K.$('#'+zone+'-zone');if(target){target.classList.add('pulse');setTimeout(function(){target.classList.remove('pulse')},900)}K.sfx.ok();K.star(1,el);K.say('动作放好了！','ok');if(!K.$$('.action:not(.placed)').length){finishLevel()}}
zones.forEach(function(z){z.addEventListener('click',function(){if(selected){place(selected,z.dataset.zone);selected=null}})});
function loadLevel(){placed={};misses=0;if(level===0){actions=[{id:'action-1',zone:'eye',safe:true,art:'book'},{id:'action-2',zone:'ear',safe:true,art:'headphones'},{id:'action-3',zone:'nose',safe:true,art:'nose'},{id:'action-4',zone:'skin',safe:true,art:'hand'}];K.levels(2,0)}else{actions=[{id:'action-1',zone:'eye',safe:false,art:'rub'},{id:'action-2',zone:'ear',safe:false,art:'stick'},{id:'action-3',zone:'nose',safe:false,art:'pick'},{id:'action-4',zone:'skin',safe:false,art:'touch'}];K.levels(2,1)}render()}
function finishLevel(){busy=true;setTimeout(function(){if(level===0){level=1;busy=false;K.say('再把不安全动作换成安全做法');loadLevel()}else{K.levels(2,2);K.finish({title:'整理好了',sub:'一起保护感觉器官',again:reset})}},700)}
function reset(){level=0;busy=false;misses=0;placed={};loadLevel();K.levels(2,0);K.$('#result').textContent=''}
function start(){reset()}
K.$('#check').addEventListener('click',function(){K.sfx.tick(level);K.say('再看看剩下的动作','')});
K.onStart=start;
K.onState=function(state){if(state.demo==='reading'){K.begin();if(level!==0)level=0;loadLevel();var a=K.$('#action-1');if(a){var eye=K.$('#zones [data-zone="eye"]');a.classList.add('placed');a.style.position='absolute';a.style.left='20px';a.style.top='20px';a.style.zIndex='3';placed[a.id]=true;if(eye)eye.classList.add('teach-hl')}demoDone=true;K.say('读书坐端正，放到眼睛旁','ok')}if(state.phase==='sort'){K.begin();level=0;loadLevel();demoDone=false;K.say('把动作放到对应部位旁')}};
loadLevel();
})();

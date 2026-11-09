
(function(){
'use strict';
const $=K.$,$$=K.$$;
const images={"prepare": "__IMG:prepare__", "leave": "__IMG:leave-sequence__"};
function pic(key,alt){return '<img class="art" src="'+images[key]+'" alt="'+alt+'">'}
function guardImages(){ $$('img').forEach(im=>{im.onerror=function(){this.classList.add('broken');this.alt='图片暂不可用';if(!$('#page-media-failure')){const panel=K.el('div','media-failure','<div class="media-failure-card"><h2>图片没有加载好</h2><p>请大人帮忙，重新打开这一页。</p><button class="btn blue" aria-label="重新加载图片">↻</button></div>',K.stage());panel.id='page-media-failure';panel.querySelector('button').onclick=()=>window.location.reload();}};}); }

function msg(t,ok){K.say(t,ok?'ok':'');}
function award(el){K.sfx.ok();K.star(1,el);}
function finish(again,sub){K.finish({title:'这一页完成啦',sub:sub||'选择和操作已记录，口头表现待大人观察',again:again});}
function resetStars(){K.stars=0;const n=$('#star-n');if(n)n.textContent='0';}

let selected=null,miss=0;const slots=[$('#slot-first'),$('#slot-second')];
function move(card,target){if(!card||!target||card.classList.contains('done'))return;const expected=card.dataset.key==='prepare'?'slot-first':'slot-second';if(target.id!==expected){miss++;K.shake(card);msg(miss===1?'比较两幅动作，想想谁在为谁做准备。':'先看准备的动作，再看已经出发的动作。');return;}target.appendChild(card);card.classList.remove('chosen');card.classList.add('done');card.disabled=true;selected=null;award(card);const placed=$$('.order-slot .order-card').length;K.levels(2,placed);msg(placed===2?'两幅图已配好，按对勾看完整顺序。':'这一幅留在格中，再把另一幅图放好。');}

function reset(){resetStars();miss=0;selected=null;slots.forEach(x=>x.querySelectorAll('.order-card').forEach(c=>c.remove()));const bank=$('#order-bank');bank.innerHTML='';K.shuffle([['prepare','先备好书包'],['leave','再背包出门']]).forEach(([key,alt])=>{const el=K.el('button','tile order-card',pic(key,alt),bank);el.id='order-'+key;el.dataset.key=key;el.onclick=()=>{$$('.order-card').forEach(x=>x.classList.remove('chosen'));selected=el;el.classList.add('chosen');};K.drag(el,{enabled:()=>!el.classList.contains('done'),targets:()=>slots,onTap:()=>el.click(),onDrop:move});});slots.forEach(x=>x.onclick=e=>{if(e.target.closest('.order-card'))return;move(selected,x);});K.levels(2,0);msg('先准备，再出发。把图放进两个大格。');guardImages();}
$('#check-order').onclick=()=>{const a=slots[0].querySelector('.order-card'),b=slots[1].querySelector('.order-card');if(a&&b&&a.dataset.key==='prepare'&&b.dataset.key==='leave'){finish(reset,'图序已记录；安排的口头理由待观察。');}else{miss++;K.shake($('#order-slots'));msg(miss===1?'先看看两件事是否都放进格子。':'想一想：书包备好后，才能背着出门。');}};
$('#order-hint').onclick=()=>msg(++miss<2?'想想哪幅图是在做准备。':'先放准备书包，后放背包出门。');
K.hud({icon:'序',title:'先安排，再出发',levels:2});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='arrange'){reset();const cards=$$('.order-card');move(cards.find(x=>x.dataset.key==='prepare'),slots[0]);move(cards.find(x=>x.dataset.key==='leave'),slots[1]);}if(state.demo==='reset')reset();};K.ready({emoji:'序',title:'排好两件事',sub:'拖图，或点图再点大格'});reset();

guardImages();
})();

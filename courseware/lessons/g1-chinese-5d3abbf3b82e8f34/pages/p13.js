
(function(){
'use strict';
const $=K.$,$$=K.$$;
const images={};
function pic(key,alt){return '<img class="art" src="'+images[key]+'" alt="'+alt+'">'}
function guardImages(){ $$('img').forEach(im=>{im.onerror=function(){this.classList.add('broken');this.alt='图片暂不可用';if(!$('#page-media-failure')){const panel=K.el('div','media-failure','<div class="media-failure-card"><h2>图片没有加载好</h2><p>请大人帮忙，重新打开这一页。</p><button class="btn blue" aria-label="重新加载图片">↻</button></div>',K.stage());panel.id='page-media-failure';panel.querySelector('button').onclick=()=>window.location.reload();}};}); }

function msg(t,ok){K.say(t,ok?'ok':'');}
function award(el){K.sfx.ok();K.star(1,el);}
function finish(again,sub){K.finish({title:'这一页完成啦',sub:sub||'选择和操作已记录，口头表现待大人观察',again:again});}
function resetStars(){K.stars=0;const n=$('#star-n');if(n)n.textContent='0';}


let selected=null,placed=0,miss=0;const people=$$('.name-person');
function move(card,person){if(!card||card.classList.contains('done'))return;if(card.dataset.key!==person.dataset.key){miss++;K.shake(card);msg(miss===1?'先想想刚才听到的两个名字。':'小满是男孩，朵朵是女孩；再对照名字。');return;}person.querySelector('.name-place').appendChild(card);card.classList.add('done');card.classList.remove('chosen');selected=null;placed++;award(person);K.levels(2,placed);if(placed===2)finish(reset,'姓名配对已记录；再次认读请大人听。');}
function reset(){placed=0;miss=0;selected=null;resetStars();$$('.name-place').forEach(x=>x.innerHTML='');const bank=$('#name-cards');bank.innerHTML='';K.shuffle(['小满','朵朵']).forEach(name=>{const b=K.el('button','tile name-card',name,bank);b.dataset.key=name;b.onclick=()=>{selected=b;$$('.name-card').forEach(x=>x.classList.toggle('chosen',x===b));};K.drag(b,{targets:()=>people,enabled:()=>!b.classList.contains('done'),onTap:()=>b.click(),onDrop:move});});people.forEach(person=>person.onclick=e=>{if(e.target.closest('.name-card'))return;move(selected,person);});K.levels(2,0);msg('男孩叫小满，女孩叫朵朵。把姓名卡送过去。');}
$('#name-hint').onclick=()=>msg(++miss<2?'回想老师介绍的名字，比较卡片上的字。':'小满送给男孩，朵朵送给女孩；再跟大人读。');
K.hud({icon:'名',title:'听名字，找字卡',levels:2});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='match'){reset();move($$('.name-card').find(x=>x.dataset.key==='小满'),$('#person-boy'));}if(state.demo==='reset')reset();};K.ready({emoji:'名',title:'姓名卡找主人',sub:'听过介绍，拖卡或点卡再点人物'});reset();

guardImages();
})();

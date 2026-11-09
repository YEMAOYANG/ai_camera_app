
(function(){
'use strict';
const $=K.$,$$=K.$$;
const images={"root": "__IMG:root__", "grandpa": "__IMG:grandpa__", "grandma": "__IMG:grandma__", "girl": "__IMG:girl__", "dog": "__IMG:dog__"};
function pic(key,alt){return '<img class="art" src="'+images[key]+'" alt="'+alt+'">'}
function guardImages(){ $$('img').forEach(im=>{im.onerror=function(){this.classList.add('broken');this.alt='图片暂不可用';if(!$('#page-media-failure')){const panel=K.el('div','media-failure','<div class="media-failure-card"><h2>图片没有加载好</h2><p>请大人帮忙，重新打开这一页。</p><button class="btn blue" aria-label="重新加载图片">↻</button></div>',K.stage());panel.id='page-media-failure';panel.querySelector('button').onclick=()=>window.location.reload();}};}); }

function msg(t,ok){K.say(t,ok?'ok':'');}
function award(el){K.sfx.ok();K.star(1,el);}
function finish(again,sub){K.finish({title:'这一页完成啦',sub:sub||'选择和操作已记录，口头表现待大人观察',again:again});}
function resetStars(){K.stars=0;const n=$('#star-n');if(n)n.textContent='0';}


const seq=[['grandma','老婆婆'],['girl','小姑娘'],['dog','小狗']];let next=0,miss=0,selected=null;
function join(card){if(!card||card.classList.contains('done'))return;if(card.dataset.key!==seq[next][0]){miss++;K.shake(card);msg(miss===1?'想想前一位帮手请了谁。':'老公公后接老婆婆，再接小姑娘，最后接小狗。');return;}card.classList.add('done');card.classList.remove('chosen');card.style.left=(430+next*190)+'px';card.style.top='30px';$('#helper-line').appendChild(card);selected=null;miss=0;next++;award(card);K.levels(3,next);if(next===3)finish(reset,'已读到的帮手关系已配好，教材共读待成人听。');else msg('队伍变长了，再请下一位。');}
function reset(){next=0;miss=0;selected=null;resetStars();$$('.helper-card').forEach(x=>x.remove());const bank=$('#helper-bank');K.shuffle(seq).forEach(([key,label])=>{const b=K.el('button','tile helper-card',pic(key,label),bank);b.dataset.key=key;b.onclick=()=>{if(b.classList.contains('done'))return;selected=b;$$('.helper-card').forEach(x=>x.classList.toggle('chosen',x===b));join(b);};K.drag(b,{enabled:()=>!b.classList.contains('done'),targets:()=>[$('#helper-tail')],onDrop:(e,t)=>t&&join(e)});});$('#helper-tail').onclick=()=>join(selected);K.levels(3,0);msg('想想老公公向谁求助，再把帮手接过来。');guardImages();}
$('#helper-hint').onclick=()=>msg(++miss<2?'回想教材里前后相接的关系。':'老婆婆、小姑娘、小狗，依次接在后面。');
K.hud({icon:'帮',title:'已读情节的连接线',levels:3});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='join'){reset();join($$('.helper-card').find(x=>x.dataset.key==='grandma'));}if(state.demo==='reset')reset();};K.ready({emoji:'帮',title:'让帮手加入',sub:'按已读顺序，点帮手或拖到队尾'});reset();

guardImages();
})();

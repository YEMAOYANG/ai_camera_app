
(function(){
'use strict';
const $=K.$,$$=K.$$;
const images={"boy": "__IMG:boy__", "girl": "__IMG:girl__", "blocks": "__IMG:blocks__", "paint": "__IMG:paint__", "ball": "__IMG:ball__"};
function pic(key,alt){return '<img class="art" src="'+images[key]+'" alt="'+alt+'">'}
function guardImages(){ $$('img').forEach(im=>{im.onerror=function(){this.classList.add('broken');this.alt='图片暂不可用';if(!$('#page-media-failure')){const panel=K.el('div','media-failure','<div class="media-failure-card"><h2>图片没有加载好</h2><p>请大人帮忙，重新打开这一页。</p><button class="btn blue" aria-label="重新加载图片">↻</button></div>',K.stage());panel.id='page-media-failure';panel.querySelector('button').onclick=()=>window.location.reload();}};}); }

function msg(t,ok){K.say(t,ok?'ok':'');}
function award(el){K.sfx.ok();K.star(1,el);}
function finish(again,sub){K.finish({title:'这一页完成啦',sub:sub||'选择和操作已记录，口头表现待大人观察',again:again});}
function resetStars(){K.stars=0;const n=$('#star-n');if(n)n.textContent='0';}


const topics=[['blocks','搭积木'],['paint','画画'],['ball','玩篮球']];let idx=0,miss=0,selected=null;
function give(card){if(!card)return;if(card.dataset.key!==topics[idx][0]){miss++;K.shake(card);msg(miss===1?'先听同伴刚才说了什么兴趣。':'现在的话题是'+topics[idx][1]+'，找对应的物件。');return;}const table=$('#talk-table');table.innerHTML=card.innerHTML;table.classList.add('done');award(table);idx++;K.levels(3,idx);if(idx===3){finish(reset,'话题图片已配好；真实问答和专注回应待观察。');}else{setTimeout(()=>{if(idx<3){render();}},600);}}
function render(){selected=null;miss=0;$('#topic-cue').innerHTML=pic(topics[idx][0],topics[idx][1]);$('#talk-table').innerHTML='';$('#talk-table').classList.remove('done');const bank=$('#topic-bank');bank.innerHTML='';K.shuffle(topics).forEach(([key,alt])=>{const b=K.el('button','tile topic-card',pic(key,alt),bank);b.dataset.key=key;b.onclick=()=>{selected=b;$$('.topic-card').forEach(x=>x.classList.toggle('chosen',x===b));};K.drag(b,{targets:()=>[$('#talk-table')],onTap:()=>b.click(),onDrop:(e,t)=>t&&give(e)});});msg('小满喜欢'+topics[idx][1]+'。送什么物件来接话？');guardImages();}
function reset(){idx=0;miss=0;selected=null;resetStars();K.levels(3,0);render();}
$('#talk-table').onclick=()=>give(selected);$('#talk-hint').onclick=()=>msg(++miss<2?'回想同伴正在谈什么，先接着这个话题。':'现在听到的是'+topics[idx][1]+'，找直接相关的物件。');
K.hud({icon:'话',title:'听懂，再接着聊',levels:3});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='topic'){reset();const c=$$('.topic-card').find(x=>x.dataset.key==='blocks');$('#talk-table').innerHTML=c.innerHTML;$('#talk-table').classList.add('done');}if(state.demo==='reset')reset();};K.ready({emoji:'话',title:'把话题接下去',sub:'听同伴的兴趣，把物件送到两人中间'});reset();

guardImages();
})();

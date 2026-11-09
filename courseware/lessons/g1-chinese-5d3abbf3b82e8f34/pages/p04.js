
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

const groups=[[['禾','秋'],['木','树'],['口','叶']],[['氵','江'],['艹','莲'],['宀','家']],[['讠','说'],['虫','蛙'],['夂','冬']]];
let group=0,placed=0,selected=null,miss=0;const trays=$$('.radical-house');
function drop(card,tray){if(!card||card.classList.contains('done'))return;if(card.dataset.home!==tray.dataset.home){miss++;K.shake(card);msg(miss===1?'先找两个字形里相同的部分。':'把字里的偏旁，和屋顶逐个比较。');return;}tray.appendChild(card);card.classList.remove('chosen');card.classList.add('done');selected=null;placed++;award(tray);if(placed===3){group++;if(group===3)finish(reset,'九个偏旁已分组，完整认读待大人听。');else render();}}
function render(){placed=0;selected=null;miss=0;K.levels(3,group);trays.forEach((el,i)=>{el.innerHTML='<strong>'+groups[group][i][0]+'</strong>';el.dataset.home=groups[group][i][0];el.onclick=()=>drop(selected,el);});const bank=$('#character-bank');bank.innerHTML='';K.shuffle(groups[group]).forEach(pair=>{const card=K.el('button','tile char-card',pair[1],bank);card.dataset.home=pair[0];card.onclick=()=>{$$('.char-card').forEach(x=>x.classList.remove('chosen'));selected=card;card.classList.add('chosen');};K.drag(card,{enabled:()=>!card.classList.contains('done'),targets:()=>trays,onTap:()=>card.click(),onDrop:(e,t)=>t&&drop(e,t)});});msg('看偏旁，送字卡回家。');}
function reset(){group=0;resetStars();render();}
$('#radical-hint').onclick=()=>msg(++miss<2?'看共同的部分，别只看字卡位置。':'每间屋顶的字形，就是要找的偏旁。');
K.hud({icon:'字',title:'偏旁小屋',levels:3});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='show'){group=0;render();const c=$$('.char-card').find(x=>x.textContent==='秋');drop(c,trays[0]);}if(state.demo==='reset')reset();};K.ready({emoji:'字',title:'字卡回家',sub:'点字卡再点屋子，也可以拖过去'});render();

guardImages();
})();

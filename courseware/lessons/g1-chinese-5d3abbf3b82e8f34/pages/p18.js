
(function(){
'use strict';
const $=K.$,$$=K.$$;
const images={"root": "__IMG:root__", "grandpa": "__IMG:grandpa__", "grandma": "__IMG:grandma__", "girl": "__IMG:girl__", "dog": "__IMG:dog__", "cat": "__IMG:cat__", "mouse": "__IMG:mouse__"};
function pic(key,alt){return '<img class="art" src="'+images[key]+'" alt="'+alt+'">'}
function guardImages(){ $$('img').forEach(im=>{im.onerror=function(){this.classList.add('broken');this.alt='图片暂不可用';if(!$('#page-media-failure')){const panel=K.el('div','media-failure','<div class="media-failure-card"><h2>图片没有加载好</h2><p>请大人帮忙，重新打开这一页。</p><button class="btn blue" aria-label="重新加载图片">↻</button></div>',K.stage());panel.id='page-media-failure';panel.querySelector('button').onclick=()=>window.location.reload();}};}); }

function msg(t,ok){K.say(t,ok?'ok':'');}
function award(el){K.sfx.ok();K.star(1,el);}
function finish(again,sub){K.finish({title:'这一页完成啦',sub:sub||'选择和操作已记录，口头表现待大人观察',again:again});}
function resetStars(){K.stars=0;const n=$('#star-n');if(n)n.textContent='0';}


let helper=null,joined=false,pulled=false,ending=null,selected=null;const tail=$('#story-tail');
function join(card){if(!card)return;helper=card.dataset.key;joined=true;selected=card;$$('.story-helper').forEach(x=>x.classList.toggle('chosen',x===card));tail.innerHTML=pic(helper,helper==='cat'?'续编加入的小猫':'续编加入的小鼠');tail.classList.add('has-helper');K.sfx.pick();msg('新帮手加入了。再把队尾向萝卜方向拖一拖。');guardImages();}
function pull(){if(pulled){K.sfx.pick();return;}if(!joined){msg('先选一位新帮手，再让它参与。');return;}pulled=true;tail.style.transform='translateX(-45px)';$('#story-team').style.transform='translateX(-20px)';award(tail);msg('队伍一起动了。再选一个想象的结果。');}
function end(which){if(!pulled){msg('先让帮手加入，再一起动一动。');return;}ending=which;$('#story-root').alt=which==='out'?'已完全拔出的萝卜':'仍在土里的萝卜';$('#story-root').src=which==='out'?'__IMG:root-out__':'__IMG:root__';$('#story-root').style.transform=which==='out'?'translateY(-55px) rotate(-12deg)':'';$('#story-root').style.border=which==='more'?'5px solid #4c8ddb':'';K.sfx.pick();msg(which==='out'?'你编的是拔出来啦。请大人听完整三件事。':'你编的是继续想办法。请大人听完整三件事。');}
function reset(){helper=null;joined=false;pulled=false;ending=null;selected=null;resetStars();tail.innerHTML='';tail.classList.remove('has-helper');tail.style.transform='';$('#story-team').style.transform='';$('#story-root').src='__IMG:root__';$('#story-root').alt='仍在土里的萝卜';$('#story-root').style.transform='';$('#story-root').style.border='';$$('.story-helper').forEach(x=>x.classList.remove('chosen'));K.levels(3,0);msg('这是续编，不是照念教材。选帮手，拉一拉，想结果。');}
$$('.story-helper').forEach(b=>{b.onclick=()=>join(b);K.drag(b,{targets:()=>[tail],onTap:()=>b.click(),onDrop:(e,t)=>t&&join(e)});});K.drag(tail,{enabled:()=>joined,targets:()=>[$('#story-team')],onTap:pull,onDrop:()=>pull()});tail.onclick=()=>joined?pull():join(selected);
$('#ending-out').onclick=()=>end('out');$('#ending-more').onclick=()=>end('more');$('#story-done').onclick=()=>{if(!joined||!pulled||!ending){msg('先让新帮手加入、一起行动，再选择想象结果。');return;}finish(reset,'摆图已记录；谁来、怎样帮、结果怎样，口头待观察。');};$('#story-help').onclick=()=>{K.highlight(!joined?'#new-helpers':!pulled?'#story-tail':'#story-endings');msg('帮手、行动、结果，三件事接起来就完整。');};
K.hud({icon:'编',title:'这是我的新想法',levels:3});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='story'){reset();join($('#new-cat'));pull();}if(state.demo==='reset')reset();};K.ready({emoji:'编',title:'续编一幕',sub:'谁来？怎样帮？结果怎样？'});reset();

guardImages();
})();

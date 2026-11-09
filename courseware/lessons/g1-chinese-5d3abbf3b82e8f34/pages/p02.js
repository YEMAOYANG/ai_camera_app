
(function(){
'use strict';
const $=K.$,$$=K.$$;
const images={"book-front": "__IMG:book-front__", "book-back": "__IMG:book-back__"};
function pic(key,alt){return '<img class="art" src="'+images[key]+'" alt="'+alt+'">'}
function guardImages(){ $$('img').forEach(im=>{im.onerror=function(){this.classList.add('broken');this.alt='图片暂不可用';if(!$('#page-media-failure')){const panel=K.el('div','media-failure','<div class="media-failure-card"><h2>图片没有加载好</h2><p>请大人帮忙，重新打开这一页。</p><button class="btn blue" aria-label="重新加载图片">↻</button></div>',K.stage());panel.id='page-media-failure';panel.querySelector('button').onclick=()=>window.location.reload();}};}); }

function msg(t,ok){K.say(t,ok?'ok':'');}
function award(el){K.sfx.ok();K.star(1,el);}
function finish(again,sub){K.finish({title:'这一页完成啦',sub:sub||'选择和操作已记录，口头表现待大人观察',again:again});}
function resetStars(){K.stars=0;const n=$('#star-n');if(n)n.textContent='0';}

let level=0,back=false,miss=0,demo=false,locked=false,advanceTimer=null;const goals=[true,false,true];
const book=$('#book-object');
function render(){book.src=back?'__IMG:book-back__':'__IMG:book-front__';book.alt=back?'没有太阳图案的书背面':'有太阳图案的书封面';$('#target-word').textContent=goals[level]?'反':'正';K.levels(3,level);}
function reset(){clearTimeout(advanceTimer);locked=false;$('#confirm-face').disabled=false;$('#object-stage').classList.remove('correct');level=0;back=false;miss=0;demo=false;resetStars();render();msg('听过示范后，看目标字，再翻一翻。');}
$('#change-btn').onclick=()=>{if(locked||demo)return;back=!back;render();K.sfx.pick();};
$('#confirm-face').onclick=()=>{if(demo||locked)return;if(back!==goals[level]){miss++;K.shake(book);msg(miss===1?'先比较两面有什么不同，再试试。':'太阳图案这一面是正面；翻过去是反面。');return;}locked=true;$('#confirm-face').disabled=true;$('#object-stage').classList.add('correct');award(book);msg('这一关配对好了，稍后看看新的目标。',true);advanceTimer=setTimeout(()=>{level++;miss=0;$('#object-stage').classList.remove('correct');if(level===3){finish(reset,'正面和反面已配好，认读请大人再听。');}else{locked=false;$('#confirm-face').disabled=false;back=!goals[level];render();msg('目标换了，看看现在要哪一面。');}},850);};

$('#flip-hint').onclick=()=>msg(++miss<2?'看看图案，想想两面有什么不同。':'有太阳的封面是正；背过去是反。');
K.hud({icon:'↻',title:'正面和反面',levels:3});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='closed'||state.demo==='show'){reset();demo=true;back=true;render();}if(state.demo==='reset')reset();};
K.ready({emoji:'书',title:'翻一翻',sub:'听老师说，再让书面符合大字'});render();

guardImages();
})();

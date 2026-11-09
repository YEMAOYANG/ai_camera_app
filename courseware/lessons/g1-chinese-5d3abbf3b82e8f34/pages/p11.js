
(function(){
'use strict';
const $=K.$,$$=K.$$;
const images={"spring": "__IMG:spring__", "summer": "__IMG:summer__", "autumn": "__IMG:autumn__", "winter": "__IMG:winter__", "fish": "__IMG:fish__", "frog": "__IMG:frog__", "leaf": "__IMG:leaf__"};
function pic(key,alt){return '<img class="art" src="'+images[key]+'" alt="'+alt+'">'}
function guardImages(){ $$('img').forEach(im=>{im.onerror=function(){this.classList.add('broken');this.alt='图片暂不可用';if(!$('#page-media-failure')){const panel=K.el('div','media-failure','<div class="media-failure-card"><h2>图片没有加载好</h2><p>请大人帮忙，重新打开这一页。</p><button class="btn blue" aria-label="重新加载图片">↻</button></div>',K.stage());panel.id='page-media-failure';panel.querySelector('button').onclick=()=>window.location.reload();}};}); }

function msg(t,ok){K.say(t,ok?'ok':'');}
function award(el){K.sfx.ok();K.star(1,el);}
function finish(again,sub){K.finish({title:'这一页完成啦',sub:sub||'选择和操作已记录，口头表现待大人观察',again:again});}
function resetStars(){K.stars=0;const n=$('#star-n');if(n)n.textContent='0';}


const seasons=[['spring','春天'],['summer','夏天'],['autumn','秋天'],['winter','冬天']];let season=null,count=0,selected=null;
function choose(key){season=key;$('#season-background').src={spring:'__IMG:spring__',summer:'__IMG:summer__',autumn:'__IMG:autumn__',winter:'__IMG:winter__'}[key];$('#season-background').alt=seasons.find(x=>x[0]===key)[1];$$('.season-card').forEach(x=>x.classList.toggle('chosen',x.dataset.key===key));K.sfx.pick();msg('喜欢的季节选好了，再放两幅自然小图。');}
function place(card){if(!card||count>=2)return;if(!season){msg('先从四幅景色中挑一个喜欢的季节。');return;}const im=card.querySelector('img').cloneNode();im.className='poster-sticker';im.style.left=(70+count*200)+'px';im.style.top=(100+count*25)+'px';$('#poster-stickers').appendChild(im);card.classList.remove('chosen');selected=null;count++;award(card);msg('这幅自然图进入画报啦，请大人听你的理由。');}
function reset(){season=null;count=0;selected=null;resetStars();$('#poster-stickers').innerHTML='';$('#season-background').src='__IMG:spring__';const top=$('#season-picks');top.innerHTML='';seasons.forEach(([key,label])=>{const b=K.el('button','tile season-card',pic(key,label)+'<b>'+label+'</b>',top);b.dataset.key=key;b.onclick=()=>choose(key);});const bank=$('#poster-bank');bank.innerHTML='';[['leaf','树叶'],['fish','小鱼'],['frog','青蛙']].forEach(([key,label])=>{const b=K.el('button','tile nature-card',pic(key,label),bank);b.onclick=()=>{selected=b;$$('.nature-card').forEach(x=>x.classList.toggle('chosen',x===b));};K.drag(b,{targets:()=>[$('#poster-stickers')],onTap:()=>b.click(),onDrop:(e,t)=>{if(t)place(e);}});});$('#poster-stickers').onclick=()=>place(selected);K.levels(2,0);msg('先选季节，再把两幅自然图放进画报。');guardImages();}
$('#poster-done').onclick=()=>{if(!season||count<2){msg('还可以选季节，再摆进两幅自然图。');return;}finish(reset,'画报选择已记录；季节理由待成人听。');};$('#poster-help').onclick=()=>{K.highlight(!season?'#season-picks':'#poster-bank');msg('喜好没有统一答案；选景色，再点图和画报。');};
K.hud({icon:'画',title:'季节小画报',levels:2});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='summer'){reset();choose('summer');place($$('.nature-card')[1]);}if(state.demo==='reset')reset();};K.ready({emoji:'画',title:'做自己的画报',sub:'选季节，放小图，再说说理由'});reset();

guardImages();
})();

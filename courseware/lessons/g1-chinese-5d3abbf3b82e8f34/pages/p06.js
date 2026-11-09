
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

const chars=['女','开','关','先'];let idx=0,drawing=false,hint=0;const canvas=$('#trace-canvas'),ctx=canvas.getContext('2d');
function pos(e){const r=canvas.getBoundingClientRect();return [(e.clientX-r.left)*400/r.width,(e.clientY-r.top)*400/r.height];}
canvas.addEventListener('pointerdown',e=>{e.preventDefault();drawing=true;canvas.setPointerCapture(e.pointerId);ctx.beginPath();ctx.moveTo(...pos(e));});
canvas.addEventListener('pointermove',e=>{if(!drawing)return;ctx.lineWidth=9;ctx.strokeStyle='#4d8fc3';ctx.lineCap='round';ctx.lineTo(...pos(e));ctx.stroke();});
canvas.addEventListener('pointerup',()=>{drawing=false;msg('描画留下了线条，笔顺请大人看纸笔。');});canvas.addEventListener('pointercancel',()=>drawing=false);
function render(){hint=0;ctx.clearRect(0,0,400,400);$('#faint-char').textContent=idx===0?'':chars[idx];$('#writing-grid svg').setAttribute('aria-label',idx===0?'女的撇点示意':chars[idx]+'的田字格观察');$('#writing-word').textContent=chars[idx];$('#trace-path').style.display=idx===0?'':'none';$('#trace-start').style.display=idx===0?'':'none';K.levels(4,idx);}
function reset(){idx=0;drawing=false;resetStars();render();msg('先观察撇点，再看四个字。');}
$('#clear-trace').onclick=()=>{ctx.clearRect(0,0,400,400);K.sfx.pick();};$('#next-char').onclick=()=>{award($('#writing-word'));if(idx===3)finish(reset,'四字观察已记录；纸笔与完整笔顺待观察。');else{idx++;render();msg(idx<2?'观察整体在田字格里的位置。':'观察上下两部分怎样配合。');}};
$('#writing-hint').onclick=()=>{hint++;K.highlight('#writing-grid');msg(idx===0?(hint===1?'先找绿色起点，沿着橙色线连续描画。':'向左下撇，再向右下写点，一笔连着走。'):idx===1?(hint===1?'先看上面的两横，再比较下面两笔。':'开按横、横、撇、竖，请大人看你书空。'):(hint===1?'先观察上下两部分怎样配合。':'对照教材，请大人帮看纸笔与笔顺。'));};
K.hud({icon:'笔',title:'看字形，试描画',levels:4});K.owl();K.onStart=reset;K.onState=state=>{if(state.demo==='trace'){idx=0;render();ctx.beginPath();ctx.moveTo(200,65);ctx.lineTo(125,230);ctx.quadraticCurveTo(185,258,290,320);ctx.strokeStyle='#4d8fc3';ctx.lineWidth=8;ctx.stroke();}if(state.demo==='reset')reset();};K.ready({emoji:'笔',title:'看一笔，再看四字',sub:'手指描画，箭头换字；纸笔请大人看'});render();

guardImages();
})();

(function(){
'use strict';
function create(){return {index:0,points:0,done:[],demo:false,finished:false}}
function point(state){if(!state.demo&&!state.finished)state.points++}
function clear(state){state.points=0}
function submit(state){if(state.demo||state.finished)return {ignored:true};if(state.points<8)return {ok:false,hint:'先在淡字上留下一些笔迹，再继续。'};state.done.push({word:['饱','抱'][state.index],observation:'描画操作',writingQuality:'待观察',strokeOrder:'待观察'});state.index++;state.points=0;state.finished=state.index===2;return {ok:true,finished:state.finished}}
if(typeof module!=='undefined'&&module.exports)module.exports={create:create,point:point,clear:clear,submit:submit};
if(typeof window==='undefined'||!window.K)return;
var state=create(),drawing=false,canvas=K.$('#practice-ink'),ctx=canvas.getContext('2d');
K.hud({icon:'字',title:'观察后自由描画',levels:2});K.owl();K.ready({emoji:'字',title:'饱和抱进田字格',sub:'看清两个部分，在淡字上试着描画'});
function erase(){ctx.clearRect(0,0,canvas.width,canvas.height);clear(state);drawing=false}
function display(){K.$('#practice-glyph').textContent=['饱','抱'][Math.min(state.index,1)];K.levels(2,Math.min(state.index,2));erase()}
function reset(){state=create();K.stars=0;K.$('#star-n').textContent='0';display();K.say('看左边偏旁和右边的包，再自由描画。')}
function pos(e){var r=canvas.getBoundingClientRect();return {x:(e.clientX-r.left)*canvas.width/r.width,y:(e.clientY-r.top)*canvas.height/r.height}}
canvas.addEventListener('pointerdown',function(e){if(state.demo||state.finished)return;e.preventDefault();drawing=true;var p=pos(e);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineWidth=9;ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle='#4C8DDB';point(state);canvas.setPointerCapture(e.pointerId)});
canvas.addEventListener('pointermove',function(e){if(!drawing)return;var p=pos(e);ctx.lineTo(p.x,p.y);ctx.stroke();point(state)});
canvas.addEventListener('pointerup',function(){drawing=false});canvas.addEventListener('pointercancel',function(){drawing=false});
K.$('#clear-writing').onclick=function(){erase();K.say('自己的笔迹清除了，可以重新描画。')};
K.$('#next-writing').onclick=function(){var r=submit(state);if(r.ignored)return;if(!r.ok){K.say(r.hint,'no');K.sfx.no();return}K.star(1,canvas);K.sfx.ok();if(r.finished){K.levels(2,2);K.finish({title:'描画操作完成',sub:'请拿纸笔练一练，再请大人观察字形与笔顺。',again:reset})}else{display();K.say('换一个字，先看左边偏旁哪里不同。','ok')}};
K.onStart=reset;K.onState=function(s){if(s.demo){state=create();state.demo=true;state.index=1;display();K.say('教师示范：观察抱的提手旁和右边的包。')}if(s.play)reset()};reset();
K.test=async function(){if(!K.cp)return;reset();await K.cp('初始');K.$('#next-writing').click();await K.cp('未描画提示');K.onState({demo:true});await K.cp('教师示范');reset();for(var j=0;j<2;j++){ctx.beginPath();ctx.moveTo(180,80);for(var i=0;i<16;i++){ctx.lineTo(180+i*4,80+i*17);point(state)}ctx.stroke();K.$('#next-writing').click()}await K.cp('描画操作完成');reset();await K.cp('重玩复位')};
})();

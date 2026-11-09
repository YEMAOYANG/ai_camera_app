var NestedRules={next:function(step,target){if(step===0&&target==='wet')return 1;if(step===1&&target==='table')return 2;if(step===2&&target==='inner')return 3;return step}};
if(typeof module==='object'&&module.exports){module.exports=NestedRules}else{(function(){
var step=0,misses=0,demo=-1,table=K.$('#nested-table'),straw=K.$('#nested-straw');
K.hud({icon:'',title:'给小泡泡留空间',levels:3});K.owl();
function render(){var s=demo>=0?demo:step;table.classList.toggle('wet',s>=1);table.classList.toggle('big',s>=2);table.classList.toggle('nested',s===3||demo===2);table.classList.toggle('demo',demo>=0);K.levels(3,step)}
function reset(){step=0;misses=0;demo=-1;K.stars=0;K.$('#star-n').textContent='0';render();K.say('先润湿，再按顺序尝试。')}
function act(target){demo=-1;var next=NestedRules.next(step,target);if(next===step){misses++;K.sfx.no();K.shake(straw);if(misses>=2)K.highlight(step===0?'#nested-wet':step===1?'#nested-table':'#nested-inner');K.say(misses===1?'先看看现在进行到哪一步。':step===0?'桌面还没准备好，先看看水滴。':step===1?'先有大的，再想里面的小的。':'看看外层边缘，给里面留些空间。','no');return}step=next;misses=0;render();K.sfx.ok();K.star(1,table);K.say(step===1?'桌面准备好，再来试大泡泡。':step===2?'大泡泡出现了，再找里面的空间。':'内外留着间隔，图中操作完成。','ok');if(step===3)setTimeout(function(){K.finish({title:'按顺序完成了',sub:'真实吹泡泡的方法，请和大人一起试。',again:reset})},700)}
K.$('#nested-wet').onclick=function(){act('wet')};
K.drag(straw,{enabled:function(){return step<3},targets:function(){return step<2?[table]:[K.$('#nested-inner'),K.$('#nested-edge'),K.$('#nested-outside')]},onDrop:function(el,t){act(t===table?'table':t&&t.id==='nested-inner'?'inner':t?'edge':'outside')},onTap:function(){K.say('按住吸管，再慢慢拖到实验的位置。')}});
K.onState=function(state){if(Object.prototype.hasOwnProperty.call(state,'demoStep')){var s=Number(state.demoStep);if(s===0)reset();else{demo=s;render()}}};
K.$$('img').forEach(function(im){im.addEventListener('error',function(){K.$('#nested-retry').classList.remove('hide');K.say('图片没出现，请点圆箭头重试。')})});K.$('#nested-retry').onclick=function(){location.reload()};K.onStart=reset;K.ready({title:'给小泡泡留空间',sub:'听老师说，先后顺序很重要。',emoji:'↻'});
})();}
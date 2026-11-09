var SurfaceRules={places:['table','cloth','ball','water'],visit:function(seen,id){return this.places.indexOf(id)<0||seen.indexOf(id)>=0?seen.slice():seen.concat(id)},complete:function(seen){return this.places.every(function(id){return seen.indexOf(id)>=0})}};
if(typeof module==='object'&&module.exports){module.exports=SurfaceRules}else{(function(){
var seen=[],misses=0,demo='',cards=K.$$('.station'),straw=K.$('#lab-straw');
K.hud({icon:'',title:'四个观察小站',levels:4});K.owl();
function render(){cards.forEach(function(c){var active=seen.indexOf(c.dataset.place)>=0;c.classList.toggle('stored',active);c.classList.toggle('show-bubble',active||demo===c.dataset.place)});K.levels(4,seen.length)}
function reset(){seen=[];misses=0;demo='';K.stars=0;K.$('#star-n').textContent='0';render();K.say('换一个物体，仔细看接触的地方。')}
function place(target){if(!target){misses++;K.sfx.no();K.shake(straw);if(misses>=2)K.highlight('.station');K.say(misses===1?'先看看哪些图片是可以观察的物体。':'把吸管移到物体图片里面，再试一次。','no');return}var id=target.dataset.place;if(seen.indexOf(id)>=0){K.pop(target);K.say('这个地方看过了，可以换个地方。');return}seen=SurfaceRules.visit(seen,id);demo='';render();K.sfx.ok();K.star(1,target);K.say('这里也看到了泡泡，再换个地方比较。','ok');if(SurfaceRules.complete(seen))setTimeout(function(){K.finish({title:'观察图收齐了',sub:'图像操作完成，真实发现请大人观察。',again:reset})},650)}
K.drag(straw,{targets:function(){return cards},onDrop:function(el,t){place(t)},onTap:function(){K.say('按住吸管，把它拖到物体图片上。')}});
cards.forEach(function(c){c.addEventListener('click',function(){K.pop(c);K.say('把吸管拖到这里，就能看观察示意。')})});
K.onState=function(state){if(Object.prototype.hasOwnProperty.call(state,'demoStation')){demo=String(state.demoStation||'');render();if(!demo)reset()}};
K.$$('img').forEach(function(im){im.addEventListener('error',function(){K.$('#surface-retry').classList.remove('hide');K.say('图片没出现，请点圆箭头重试。')})});K.$('#surface-retry').onclick=function(){location.reload()};
K.onStart=reset;K.ready({title:'四个观察小站',sub:'听老师说，换个地方看。',emoji:'↻'});
})();}
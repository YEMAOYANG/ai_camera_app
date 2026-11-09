(function(){
var lab=K.$('#bird-lab'),bird=K.$('#bird-token'),goal=lab.dataset.goal;
var locations={start:[160,230],in:[557,100],on:[665,200],under:[557,375]};
var relation='start',misses=0,playing=false,busy=false,selected=false,timer=null;
K.hud({icon:'',title:'小鸟的位置',levels:1});K.owl();
K.ready({emoji:'图片暂未打开',title:'移动小鸟',sub:'先听老师，再把小鸟放到合适的位置'});
function clearTimer(){if(timer!==null){clearTimeout(timer);timer=null}}
function moveTo(value){relation=value;var pos=locations[value];bird.style.left=pos[0]+'px';bird.style.top=pos[1]+'px';bird.classList.toggle('in-hat',value==='in');bird.classList.remove('selected');selected=false;bird.dataset.relation=value}
function clearHints(){lab.classList.remove('hint-one','hint-two')}
function reset(){clearTimer();misses=0;playing=true;busy=false;selected=false;lab.classList.remove('demo','locked','done');clearHints();moveTo('start');K.stars=0;K.$('#star-n').textContent='0';K.levels(1,0);K.say('把小鸟移到老师说的位置。')}
function demonstrate(value){clearTimer();playing=false;busy=false;lab.classList.remove('done');lab.classList.add('demo','locked');clearHints();moveTo(value)}
function attempt(value){if(!playing||busy)return;clearTimer();moveTo(value);if(value!==goal){misses++;K.sfx.no();lab.classList.add('hint-one');if(misses>1)lab.classList.add('hint-two');K.say(misses===1?'再看看小鸟与帽子的位置。':misses===2?'先看帽子边界，再看鸟在哪里。':'看老师再摆一次，然后自己试。','no');if(misses>=3){busy=true;timer=setTimeout(function(){moveTo(goal);K.highlight('#hat-shell');timer=setTimeout(function(){moveTo('start');busy=false;clearHints();misses=0},1450)},800)}else timer=setTimeout(function(){moveTo('start')},1500);return}
 busy=true;playing=false;clearHints();lab.classList.add('done','locked');K.levels(1,1);K.star(1,bird);K.sfx.ok();K.say('小鸟的位置和老师说的一样。','ok');timer=setTimeout(function(){K.finish({title:'位置对应完成',sub:'你听懂并摆出了这个位置。会不会说，请家人听一听。',again:reset})},1000)}
K.$$('.landing').forEach(function(button){button.onclick=function(){if(!playing||busy)return;attempt(button.dataset.relation)}});
bird.onclick=function(){if(!playing||busy)return;selected=!selected;bird.classList.toggle('selected',selected);K.sfx.pick()};
K.drag(bird,{enabled:function(){return playing&&!busy},targets:function(){return K.$$('.landing')},onDrop:function(_bird,target){if(target)attempt(target.dataset.relation);else{bird.classList.remove('selected');selected=false}},onTap:function(){if(!playing||busy)return;selected=true;bird.classList.add('selected')}});
K.onStart=reset;
K.onState=function(state){if(state.demo&&locations[state.demo])demonstrate(state.demo);if(state.play)reset()};
K.$$('#bird-lab img').forEach(function(img){img.onerror=function(){playing=false;clearTimer();lab.classList.add('locked');K.$('#picture-error').hidden=false}});
moveTo('start');lab.classList.add('demo','locked');
window.lessonPosition={attempt:attempt,reset:reset,demonstrate:demonstrate,state:function(){return{goal:goal,relation:relation,misses:misses,playing:playing,busy:busy,stars:K.stars}},locations:locations};
})();

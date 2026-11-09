(function(){
var pics={dog:{whole:'__IMG:dog__',early:'__IMG:puppy__',late:'__IMG:dog__'},hen:{whole:'__IMG:hen__',early:'__IMG:chick__',late:'__IMG:hen__'}},animals=['dog','hen'],level=0,step=0,tries=0,phase='play',busy=false,epoch=0,missing=false;
var early=K.$('#grow-early'),late=K.$('#grow-late'),animal=K.$('#grow-animal'),buttons=K.$$('#grow-choices button');
K.hud({icon:'◉',title:'把长大的故事排出来',levels:2});K.owl();K.ready({emoji:'◉',title:'把长大的故事排出来',sub:'先幼小，再长大，动物别换错',btn:'start-btn'});
K.$$('#grow-board img').forEach(function(im){im.onerror=function(){missing=true;im.style.visibility='hidden';K.say('图片暂未载入，请重新打开本页')}});
function clear(){early.innerHTML='';late.innerHTML='';animal.src=pics[animals[level]].whole;animal.alt=level===0?'这一轮是狗':'这一轮是鸡'}
function fill(age){var target=age==='early'?early:late;target.innerHTML='';var im=K.el('img','',null,target);im.src=pics[animals[level]][age];im.alt=age==='early'?'幼小个体':'长大的成体'}
function reset(){epoch++;level=0;step=0;tries=0;phase='play';busy=false;clear();K.shuffle(buttons).forEach(function(b){K.$('#grow-choices').appendChild(b)});K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);K.say('先看这一轮的动物，再排幼小到长大')}
function choose(button){if(!K.started||busy||phase!=='play'||missing)return;var age=step===0?'early':'late';if(button.dataset.animal!==animals[level]||button.dataset.age!==age){tries++;K.sfx.no();K.shake(button);if(tries===1)K.say('先确认动物，再想前后是怎样变化的','no');else if(tries===2)K.say('同一种动物，先幼小，再长成成体','no');else{K.highlight('#grow-'+(animals[level]==='dog'?(age==='early'?'puppy':'dog'):(age==='early'?'chick':'hen')));K.say('老师示范这一张，再由你放进相框','no')}return}
tries=0;fill(age);K.sfx.ok();step++;K.say('前后是同一种动物，排出长大的线索','ok');if(step<2)return;busy=true;K.star(1,button);var token=epoch;setTimeout(function(){if(token!==epoch)return;if(level===1){K.levels(2,2);K.finish({title:'两种动物的长大排好了',sub:'成长示意帮助理解，真实变化还要继续观察',again:reset});return}level++;step=0;busy=false;clear();K.levels(2,level);K.say('换成鸡，仍然从幼小排到长大')},1000)}
buttons.forEach(function(b){b.addEventListener('click',function(){choose(b)})});K.$('#grow-reset').addEventListener('click',reset);K.onState=function(s){if(s.demo){phase='demo';clear();if(s.demo==='early')fill('early');if(s.demo==='late'){fill('early');fill('late')}}if(s.phase==='play')reset()};K.onStart=reset;reset();
})();

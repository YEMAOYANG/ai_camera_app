(function(){
'use strict';
var tasks=[{word:'抱',image:'child-hug',group:'hand',alt:'孩子抱玩具'},{word:'踢',image:'child-kick',group:'foot',alt:'孩子用脚踢球'},{word:'吹',image:'child-blow',group:'mouth',alt:'孩子用嘴吹泡泡'}];
function create(){return {level:0,miss:0,done:[],demo:false,finished:false}}
function choose(s,group){if(s.demo||s.finished)return {ignored:true};var t=tasks[s.level];if(group!==t.group){s.miss++;return {ok:false,hint:s.miss===1?'先看动作，用到了身体的哪里？':'做一做这个动作，再看三个形旁的线索。'}}s.done.push(t);s.level++;s.miss=0;s.finished=s.level===tasks.length;return {ok:true,finished:s.finished}}
if(typeof module!=='undefined'&&module.exports)module.exports={tasks:tasks,create:create,choose:choose};
if(typeof window==='undefined'||!window.K)return;
var s=create(),busy=false,selected=false,timer,urls={'child-hug':'__IMG:child-hug__','child-kick':'__IMG:child-kick__','child-blow':'__IMG:child-blow__'};
K.hud({icon:'字',title:'给动作图分家',levels:3});K.owl();K.ready({emoji:'字',title:'动作图送到哪一家',sub:'拖到形旁柜；也可以点图，再点柜子'});
function picture(parent,t){var im=K.el('img','',null,parent);im.src=urls[t.image];im.alt=t.alt;im.onerror=function(){im.style.display='none';var box=K.el('div','action-failure','图片没有打开',parent),b=K.el('button','btn sm','重试图片',box);b.onclick=function(e){e.stopPropagation();box.remove();im.style.display='';im.src=urls[t.image]}}}
function homes(){K.$$('.radical-home').forEach(function(home){var group=home.dataset.group,holder=K.$('.home-picture',home),t=s.done.find(function(d){return d.group===group});holder.innerHTML='';home.classList.toggle('stored',!!t);if(t){picture(holder,t);K.el('strong','',t.word,holder)}})}
function render(t){var c=K.$('#action-card');c.innerHTML='';c.classList.remove('selected');c.setAttribute('aria-label',t.alt+'，可拖动');picture(c,t);K.el('b','',t.word,c);homes();K.levels(3,Math.min(s.level,3));selected=false}
function reset(){clearTimeout(timer);s=create();busy=false;K.stars=0;K.$('#star-n').textContent='0';render(tasks[0]);K.say('看图里的动作，想口、手、脚的线索。')}
function answer(group){if(busy)return;var r=choose(s,group);if(r.ignored)return;if(!r.ok){K.sfx.no();K.say(r.hint,'no');return}busy=true;homes();K.star(1,K.$('#'+group+'-home'));K.sfx.ok();K.say('动作图留在对应的形旁柜里啦。','ok');timer=setTimeout(function(){busy=false;if(s.finished){K.levels(3,3);K.finish({title:'动作图找到家啦',sub:'形旁提示大致意思，还要联系具体词语。',again:reset})}else render(tasks[s.level])},1250)}
K.$$('.radical-home').forEach(function(home){home.onclick=function(){if(selected)answer(home.dataset.group);else K.say('先点动作图，再点你选的形旁柜。')}});
K.drag(K.$('#action-card'),{enabled:function(){return !s.demo&&!busy&&!s.finished},targets:function(){return K.$$('.radical-home')},onDrop:function(el,target){if(target)answer(target.dataset.group)},onTap:function(){selected=true;K.$('#action-card').classList.add('selected');K.say('已经选中动作图，再点相关的形旁柜。')}});
K.onStart=reset;K.onState=function(st){if(st.demo){clearTimeout(timer);s=create();s.demo=true;busy=false;s.done=[tasks[2]];render(tasks[2]);K.say('教师示范：用嘴吹，把吹图送到口字旁柜。')}if(st.play)reset()};reset();
K.test=async function(){if(!K.cp)return;reset();await K.cp('初始');answer('foot');await K.cp('首次错误提示');K.onState({demo:true});await K.cp('教师示范');reset();for(var i=0;i<3;i++){answer(tasks[s.level].group);await K.wait(1300)}await K.cp('答对完成');reset();await K.cp('重玩复位')};
})();

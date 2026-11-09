(function(){
 var order=['listen','hand','speak'];
 var rules={fresh:function(){return {steps:[],misses:0}},choose:function(s,key){if(s.steps.indexOf(key)>=0||s.steps.length===3)return s;return key===order[s.steps.length]?{steps:s.steps.concat(key),misses:0}:{steps:s.steps.slice(),misses:s.misses+1}}};
 window.TurnRules=rules;if(window.__RULES_ONLY__)return;
  var mediaBlocked=false;function mediaFailure(){mediaBlocked=true;K.$('#lesson-media-error').classList.remove('hide')}
  K.$$('#play img').forEach(function(im){im.addEventListener('error',mediaFailure);if(im.getAttribute('src')&&im.complete&&im.naturalWidth===0)mediaFailure()});
  K.$('#lesson-media-retry').addEventListener('click',function(){window.location.reload()});

 var s=rules.fresh(),demo=false,token=0,cards=K.$$('.turn-card'),slots=K.$$('.turn-slot'),images={listen:'__IMG:listen__',hand:'__IMG:raise-hand__',speak:'__IMG:speak-turn__'};
 function paint(){var shown=demo?order:s.steps;slots.forEach(function(slot,i){var im=K.$('img',slot),key=shown[i];slot.classList.toggle('filled',!!key);im.classList.toggle('hide',!key);if(key){im.src=images[key];im.alt={listen:'先倾听',hand:'举手等待',speak:'点到后清楚说'}[key]}});cards.forEach(function(b){b.disabled=demo||s.steps.indexOf(b.dataset.step)>=0;b.classList.toggle('stored',b.disabled)});K.levels(3,s.steps.length)}
 function reset(){token++;s=rules.fresh();demo=false;K.stars=0;K.$('#star-n').textContent='0';K.$('#turn-demo').classList.add('hide');paint();K.say('听完别人的话，再想一想下一步。');}
 function choose(key){if(mediaBlocked||demo)return;var n=s.steps.length;s=rules.choose(s,key);if(s.steps.length===n){K.sfx.no();K.say(s.misses===1?'再想一想，谁还没有说完？':s.misses===2?'把听和说的先后分清楚。':'先倾听，再举手等点到，最后清楚说。','no');return;}
 paint();K.star(1,slots[n]);K.sfx.ok();K.say(s.steps.length===1?'先让同学把话说完。':s.steps.length===2?'想补充先举手，还要等老师点到。':'轮到自己，再把想法清楚说出来。','ok');if(s.steps.length===3){var t=token;setTimeout(function(){if(t===token&&!demo)K.finish({title:'交流有先后',sub:'听完、举手等待、点到再清楚说',again:reset})},900)}}
 cards.forEach(function(b){b.addEventListener('click',function(){if(!b.disabled)choose(b.dataset.step)})});
 K.onState=function(v){if(v.mode==='demo'){token++;demo=true;K.$('#turn-demo').classList.remove('hide');paint();K.say('老师示范：先听，再举手等待，点到后清楚说。');}else if(v.mode==='practice')reset()};
 K.hud({icon:'',title:'让每个人把话说完',levels:3});K.owl();reset();K.ready({title:'让每个人把话说完',sub:'听老师讲，把动作依次送到上面',emoji:'图片暂未载入',onStart:function(){}});
})();

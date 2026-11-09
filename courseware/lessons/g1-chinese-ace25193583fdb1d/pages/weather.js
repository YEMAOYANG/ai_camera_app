(function(){
K.hud({icon:'叶',title:'动作找到图',levels:4});K.owl();
var targets=K.$$('.weather-target'),words=K.$$('.weather-word'),selected=null,done=0,miss=0,finished=false;
function reset(){done=0;miss=0;selected=null;finished=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(4,0);targets.forEach(function(t){t.classList.remove('placed');var prefix=t.querySelector('img').alt;t.querySelector('span').textContent=prefix+' _'});words.forEach(function(w){w.disabled=false;w.classList.remove('selected')});K.say('把动作字送到图片里。')}
function choose(w){if(w.disabled)return;selected=w;words.forEach(function(x){x.classList.toggle('selected',x===w)});K.sfx.pick()}
function place(w,t){if(!w||w.disabled||!t||t.classList.contains('placed'))return;if(w.textContent!==t.dataset.key){miss++;K.shake(t);K.sfx.no();K.say(miss===1?'先看图里发生了什么，再试一试。':miss===2?'回想老师带读的动作词。':'看示范，再把字送过去。','no');if(miss>=3)K.highlight('#'+targets.find(function(x){return x.dataset.key===w.textContent}).id);return}
t.classList.add('placed');t.querySelector('span').textContent=t.querySelector('img').alt+w.textContent;w.disabled=true;w.classList.remove('selected');selected=null;miss=0;done++;K.star(1,t);K.sfx.ok();K.levels(4,done);K.say('字进入图里，短语完整了。','ok');if(done===4&&!finished){finished=true;setTimeout(function(){K.finish({title:'四季连起来了',sub:'看图想词语，继续练习。',again:reset})},700)}}
words.forEach(function(w){K.drag(w,{enabled:function(){return!w.disabled},targets:function(){return targets.filter(function(t){return!t.classList.contains('placed')})},onTap:choose,onDrop:place})});
targets.forEach(function(t){t.onclick=function(){place(selected,t)}});
K.onState=function(state){if(typeof state.demo==='boolean')K.$('#weather-demo').classList.toggle('demonstrating',state.demo)};
K.onStart=reset;K.ready({emoji:'✦',title:'让动作找到图',sub:'看图片，把动作字送过去。'});reset();
})();

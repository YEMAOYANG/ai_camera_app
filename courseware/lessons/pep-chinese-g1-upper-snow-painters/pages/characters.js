(function(){
var chars=['的','家','鸡','竹','牙','用','几','步','没','参','加'],level=0,miss=0,busy=false,timer,cards=K.$$('.letter-card'),bank=K.$('#character-bank'),album=K.$('#character-album'),target=K.$('#character-target');
K.hud({icon:'字',title:'把同一个字放到一起',levels:11});K.owl();K.ready({emoji:'◌',title:'把同一个字放到一起',sub:'看字形，把相同的卡放进字册'});
function values(c){var a=K.shuffle([c,chars[(chars.indexOf(c)+3)%chars.length],chars[(chars.indexOf(c)+6)%chars.length]]);cards.forEach(function(b,i){bank.appendChild(b);b.disabled=false;b.textContent=a[i];b.dataset.char=a[i];b.classList.remove('hint')})}
function show(){clearTimeout(timer);busy=false;miss=0;target.textContent=chars[level];values(chars[level]);K.levels(chars.length,level);K.say('从上到下比字形，找到完全相同的字。')}
function reset(){level=0;K.stars=0;K.$('#star-n').textContent='0';show()}
function choose(c){if(!K.started||busy||c.disabled)return;if(c.dataset.char!==chars[level]){miss++;K.sfx.no();K.shake(c);K.say(miss===1?'先看大字，再比卡片。':miss===2?'把上面和下面都比一比。':'看看相同字形的提示，再试一次。','no');if(miss>=3)cards.find(function(b){return b.dataset.char===chars[level]}).classList.add('hint');return}busy=true;album.appendChild(c);c.disabled=true;c.classList.remove('hint');K.sfx.ok();K.star(1,c);K.say('两个字形完全相同。','ok');timer=setTimeout(function(){level++;if(level===chars.length){K.levels(chars.length,level);K.finish({title:'字卡配好了',sub:'请家人再听你认读',again:reset})}else show()},1000)}
cards.forEach(function(c){c.addEventListener('click',function(){choose(c)});K.drag(c,{enabled:function(){return K.started&&!busy&&!c.disabled},targets:function(){return [album]},onDrop:function(el,t){if(t)choose(el)}})});
K.onStart=reset;K.onState=function(s){if(s.demo==='home'){reset();busy=true;target.textContent='家';values('家');var c=cards.find(function(b){return b.dataset.char==='家'});album.appendChild(c);c.disabled=true;K.say('相同的家放到一起。')}if(s.phase==='play')reset()};
})();

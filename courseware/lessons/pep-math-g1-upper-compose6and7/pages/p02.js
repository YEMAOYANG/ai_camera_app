(function(){
var sides=[-1,-1,-1,-1,-1,-1],saved=[],miss=0,busy=false,demonstrating=false,timer;
K.hud({icon:'◉',title:'六颗圆片分两组',levels:3});K.owl();K.ready({emoji:'◉',title:'六颗圆片分两组',sub:'拖一拖，也能点一下换边'});
function count(side){return sides.filter(function(v){return v===side}).length}
function render(){
 ['#left-beads','#right-beads','#loose-pieces'].forEach(function(s){K.$(s).innerHTML=''});
 K.$('#left-count').textContent=count(0)||'';K.$('#right-count').textContent=count(1)||'';
 sides.forEach(function(side,i){var parent=K.$(side===0?'#left-beads':side===1?'#right-beads':'#loose-pieces');var b=K.el('button','piece bead','<img src="__IMG:bead__" alt="">',parent);b.id='piece-'+(i+1);b.setAttribute('aria-label','圆片'+(i+1)+'，点一下换边');b.querySelector('img').onerror=function(){this.style.visibility='hidden';b.classList.add('fallback')};
 K.drag(b,{enabled:function(){return !busy&&!demonstrating},targets:function(){return [K.$('#tray-left'),K.$('#tray-right')]},onDrop:function(el,target){if(!target)return;move(i,target.id==='tray-left'?0:1)},onTap:function(){move(i,sides[i]===0?1:0)}})});
 K.$('#saved-splits').innerHTML='';for(var j=0;j<3;j++)K.el('div','saved-card'+(saved[j]?' filled':''),saved[j]?saved[j].split('|').join(' · '):'?',K.$('#saved-splits'));
 K.levels(3,saved.length);K.$('#reset-split').disabled=busy||demonstrating||sides.every(function(side){return side===-1});K.$('#save-split').disabled=busy||demonstrating;
}
function move(i,side){if(busy||demonstrating)return;sides[i]=side;K.sfx.pick();render()}
function clearBoard(){sides=[-1,-1,-1,-1,-1,-1];miss=0;busy=false;render();K.say('把六颗圆片都放好，两边都要有。')}
function resetAll(){clearTimeout(timer);saved=[];demonstrating=false;K.stars=0;K.$('#star-n').textContent='0';clearBoard()}
function wrong(){miss++;K.sfx.no();K.highlight(miss===1?'#whole-total':'#saved-splits');K.say(miss===1?'再看看，六颗都分好了吗？两边都有吗？':miss===2?'想想怎样换一种分法，别再保存同一种。':'看一次新的分法示范，再数两边。','no');if(miss>=3){var a=[1,2,3,4,5].filter(function(n){return saved.indexOf(n+'|'+(6-n))<0})[0];sides=sides.map(function(side,i){return i<a?0:1});render();K.highlight('#tray-left');K.highlight('#tray-right');miss=0}}
K.$('#save-split').onclick=function(){if(busy||demonstrating)return;var a=count(0),b=count(1),key=a+'|'+b;if(a+b!==6||a===0||b===0||saved.indexOf(key)>=0){wrong();return}saved.push(key);miss=0;busy=true;render();K.star(1,K.$('#save-split'));K.sfx.ok();K.say('分成两组，合起来还是六颗。','ok');timer=setTimeout(function(){if(saved.length===3)K.finish({title:'找到了三种分法',sub:'还能想到别的分法吗？',again:resetAll});else clearBoard()},900)};
K.$('#reset-split').onclick=function(){if(!busy&&!demonstrating)clearBoard()};
K.onStart=resetAll;K.onState=function(state){clearTimeout(timer);if(typeof state.demoLeft==='number'){demonstrating=true;busy=false;var a=Math.max(1,Math.min(5,state.demoLeft));sides=sides.map(function(v,i){return i<a?0:1});render();K.say('老师把六颗分成两部分，数一数每边。')}if(state.play)resetAll()};render();
})();

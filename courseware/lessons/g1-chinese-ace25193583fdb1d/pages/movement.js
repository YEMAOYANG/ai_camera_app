(function(){
K.hud({icon:'林',title:'看位置，懂词语',levels:2});K.owl();
var fish=K.$('#move-fish'),bird=K.$('#move-bird'),air=K.$('#move-air'),woods=K.$('#move-woods'),selected=null,count=0,miss=0,finished=false;
function reset(){selected=null;count=0;miss=0;finished=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);[fish,bird,air,woods].forEach(function(e){e.classList.remove('placed','selected')});fish.style.left='345px';fish.style.top='360px';bird.style.left='620px';bird.style.top='365px';K.say('移动动物，看看位置怎样变。')}
function choose(a){if(a.classList.contains('placed'))return;selected=a;[fish,bird].forEach(function(e){e.classList.toggle('selected',e===a)});K.sfx.pick()}
function move(a,t){if(!a||!t||a.classList.contains('placed'))return;var valid=(a===fish&&t===air)||(a===bird&&t===woods);if(!valid){miss++;K.shake(a);K.sfx.no();K.say(miss===1?'看清水和树林的位置，再试试看。':miss===2?'想一想，是到外面，还是到里面。':'看示范的位置，再移动一次。','no');if(miss>=3)K.highlight('#'+(a===fish?'move-air':'move-woods'));return}
a.classList.remove('selected');a.classList.add('placed');t.classList.add('placed');a.style.left=(t.offsetLeft+52)+'px';a.style.top=(t.offsetTop+12)+'px';selected=null;miss=0;count++;K.star(1,a);K.sfx.ok();K.levels(2,count);K.say(a===fish?'鱼从水里出来了。':'鸟到了树林里面。','ok');if(count===2&&!finished){finished=true;setTimeout(function(){K.finish({title:'位置变了，词义清楚了',sub:'出是到外面，入是到里面。',again:reset})},850)}}
[fish,bird].forEach(function(a){K.drag(a,{enabled:function(){return!a.classList.contains('placed')},targets:function(){return[air,woods]},onTap:choose,onDrop:move})});[air,woods].forEach(function(t){t.onclick=function(){move(selected,t)}});
K.onState=function(state){if(state.demo){var e=K.$('#move-sample');if(state.demo==='clear'){e.classList.add('hide');return}e.classList.remove('hide');e.src=state.demo==='fish'?'__IMG:red-fish__':'__IMG:blue-bird__';var t=state.demo==='fish'?air:woods;e.style.left=(t.offsetLeft+70)+'px';e.style.top=(t.offsetTop+12)+'px'}};
K.onStart=reset;K.ready({emoji:'✦',title:'鱼出水，鸟入林',sub:'移动动物，看看位置。'});reset();
})();

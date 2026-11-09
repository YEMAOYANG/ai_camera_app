K.hud({icon:'◆',title:"摆出熟悉的地方",levels:3});K.owl();
function cleanStars(){K.stars=0;K.$('#star-n').textContent='0';}
function finished(){K.finish({title:'活动完成',sub:'记录的是这次动手过程',again:reset});}

var kinds=['building','tree','slide'],selected=0,used={},timer=null;
function choose(i){selected=i;kinds.forEach(function(k,j){K.$('#stamp-'+k).classList.toggle('selected',j===i)});}
function reset(){clearTimeout(timer);used={};choose(0);cleanStars();K.levels(3,0);K.$$('.map-slot').forEach(function(b){b.innerHTML='';b.classList.remove('placed')});K.say('选择图片，再点空位置放进去。');}
function place(slot,demo){if(slot.classList.contains('placed')){K.say('这儿已有图片，换一个空位置，或重新布置。');K.shake(slot);return;}var k=kinds[selected],im=K.el('img','',null,slot);im.src=K.$('#stamp-'+k+' img').src;im.alt=k==='building'?'教室':k==='tree'?'树':'滑梯';slot.classList.add('placed');K.sfx.drop();if(demo)return;if(!used[k]){used[k]=true;K.star(1,slot);}var n=Object.keys(used).length;K.levels(3,n);if(n===3){K.say('三个熟悉的地方已经放进图里。','ok');timer=setTimeout(finished,700);}else{choose(kinds.findIndex(function(x){return !used[x]}));K.say('还可以再选一个熟悉的地方放进来。','ok');}}
kinds.forEach(function(k,i){K.$('#stamp-'+k).onclick=function(){choose(i);K.sfx.pick()};});K.$$('.map-slot').forEach(function(b){b.onclick=function(){place(b,false)};});K.$('#map-reset').onclick=reset;
K.onState=function(state){if(state.demo){reset();choose(0);place(K.$('#map-slot-1'),true);K.highlight('#map-slot-1');}else if(state.demo===false){reset();}};
K.onStart=reset;K.ready({emoji:'◆',title:'摆出熟悉的地方',sub:'图片放进画里，就能介绍幼儿园'});

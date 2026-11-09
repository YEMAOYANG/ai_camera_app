K.hud({icon:'◆',title:"一棵一棵数",levels:3});K.owl();
function cleanStars(){K.stars=0;K.$('#star-n').textContent='0';}
function finished(){K.finish({title:'活动完成',sub:'记录的是这次动手过程',again:reset});}

var level=0,amounts=[3,4,5],marked={},wrong=0,timer=null,busy=false;
function draw(){marked={};wrong=0;busy=false;K.$$('.tree-item').forEach(function(b,i){b.style.display=i<amounts[level]?'block':'none';b.classList.remove('counted');});K.$('#count-number').textContent='0';K.levels(3,level);K.say('每棵树点一次，再选一共有几棵。');}
function reset(){clearTimeout(timer);level=0;cleanStars();draw();}
K.$$('.tree-item').forEach(function(b,i){b.onclick=function(){if(busy||marked[i])return;marked[i]=true;b.classList.add('counted');K.$('#count-number').textContent=String(Object.keys(marked).length);K.sfx.tick(Object.keys(marked).length);};});
[3,4,5].forEach(function(n){K.$('#count-choice-'+n).onclick=function(){if(busy)return;if(Object.keys(marked).length<amounts[level]){wrong++;K.say('先逐棵点数，别漏掉没标记的树。','no');K.shake(K.$('#count-field'));return;}if(n!==amounts[level]){wrong++;K.say(wrong===1?'再看点数的记录，最后数到了几？':'用手指沿着标记，从一开始再数一遍。','no');K.sfx.no();if(wrong>=3)K.highlight('#count-number');return;}busy=true;K.star(1,K.$('#count-choice-'+n));K.sfx.ok();K.say('点数记录和全部树的数量对上了。','ok');level++;K.levels(3,level);timer=setTimeout(function(){if(level===3)finished();else draw();},650);};});
K.onState=function(state){if(state.demo){reset();var c=Number(state.count)||0;K.$$('.tree-item').forEach(function(b,i){if(i<c){marked[i]=true;b.classList.add('counted');}});K.$('#count-number').textContent=String(c);}else if(state.demo===false){reset();}};
K.onStart=reset;K.ready({emoji:'◆',title:'一棵一棵数',sub:'点过留下标记，不漏也不重复'});

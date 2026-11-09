(function(){
var slots={high:{x:145,y:306},mid:{x:245,y:372},low:{x:335,y:432}},rounds=['mid','high'],index=0,tries=0,busy=false,phase='play',selected=false,epoch=0;
var steel=K.$('#compare-steel'),wood=K.$('#compare-wood'),placed=K.$('#compare-placed'),record=K.$('#compare-record'),targets=K.$$('.compare-target');
K.hud({icon:'◉',title:'搭好比较实验',levels:2});K.owl();K.ready({emoji:'◉',title:'搭好比较实验',sub:'木球与钢球，保持相同的起点',btn:'start-btn'});
function put(el,p){el.style.left=(p.x-24)+'px';el.style.top=(p.y-24)+'px'}
function show(){var p=slots[rounds[index]];put(steel,{x:p.x,y:p.y-255});placed.classList.add('hide');wood.classList.remove('hide','selected');selected=false;targets.forEach(function(t){t.classList.remove('correct')})}
function reset(){epoch++;index=0;tries=0;busy=false;phase='play';selected=false;record.innerHTML='';K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);show();K.say('先看钢球的起点，把木球放到相同位置')}
function place(pos){put(placed,slots[pos]);placed.classList.remove('hide');wood.classList.add('hide');K.$('#compare-target-'+pos).classList.add('correct')}
function save(){var pair=K.el('span','',null,record);K.el('i','',null,pair);K.el('i','wood',null,pair);pair.setAttribute('aria-label','同一起点的一对球')}
function match(t){if(!K.started||busy||phase!=='play'||!t)return;var pos=t.dataset.position;if(pos!==rounds[index]){tries++;K.sfx.no();K.shake(wood);if(tries===1)K.say('把上下两条相同斜轨的起点比一比','no');else if(tries===2)K.say('比较球的材质时，放手位置也要相同','no');else{K.highlight('#compare-target-'+rounds[index]);K.say('看看老师提示，再亲手放一次','no')}return}busy=true;place(pos);save();K.star(1,t);K.sfx.ok();K.say('两个球的起点对齐，准备好再观察','ok');var token=epoch;setTimeout(function(){if(token!==epoch)return;index++;K.levels(2,index);if(index===rounds.length)K.finish({title:'比较实验搭好了',sub:'只换材质，实际结果要观察',again:reset});else{tries=0;busy=false;show();K.say('钢球换了起点，木球也要重新对齐')}},900)}
K.drag(wood,{enabled:function(){return K.started&&!busy&&phase==='play'},targets:function(){return targets},onTap:function(){selected=true;wood.classList.add('selected');K.sfx.pick()},onDrop:function(el,t){match(t)}});targets.forEach(function(t){t.addEventListener('click',function(){if(selected)match(t)})});K.$('#compare-reset').addEventListener('click',reset);
wood.addEventListener('keydown',function(e){if((e.key==='Enter'||e.key===' ')&&K.started&&!busy&&phase==='play'){e.preventDefault();selected=true;wood.classList.add('selected');K.sfx.pick()}});
K.onState=function(state){if(state.demo==='same-start'){epoch++;phase='demo';index=0;show();place('mid');record.innerHTML='';save()}if(state.phase==='play')reset()};K.onStart=reset;reset();
})();

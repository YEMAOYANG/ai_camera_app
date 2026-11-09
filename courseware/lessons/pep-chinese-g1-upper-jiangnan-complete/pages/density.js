(function(){
var level=0,tries=0,busy=false,selected=false,timer;
var ponds=[K.$('#pond-1'),K.$('#pond-2')],fish=K.$('#fish');
K.hud({icon:'🌿',title:'莲叶有多少',levels:2});K.owl();K.ready({emoji:'🌿',title:'莲叶有多少',sub:'看看哪边叶子多',btn:'start-btn'});
var positions=[[58,35],[173,20],[288,20],[403,35],[95,131],[225,128],[355,131]];
function draw(){var counts=level===0?[3,6]:[7,2];ponds.forEach(function(p,j){p.innerHTML='';p.classList.remove('bloom');for(var i=0;i<counts[j];i++){var e=K.el('div','leaf','',p);if(j===0&&i===0)e.id='leaf-1';e.style.left=positions[i][0]+'px';e.style.top=positions[i][1]+'px'}});fish.style.left='546px';fish.style.top='383px';selected=false;tries=0;busy=false;K.levels(2,level);K.say('看看哪边莲叶更茂盛，把鱼送过去')}
function move(side){fish.style.left=(side===0?230:862)+'px';fish.style.top='248px';ponds[side].classList.add('bloom')}
function choose(side){if(!K.started||busy)return;var answer=level===0?1:0;if(side===answer){busy=true;move(side);K.sfx.ok();K.star(1,fish);K.say('莲叶挨得密密的，真茂盛！','ok');timer=setTimeout(function(){if(level===0){level=1;draw()}else{K.levels(2,2);K.finish({title:'莲叶真茂盛',sub:'想象莲叶田田',again:reset})}},1500)}else{tries++;K.sfx.no();K.shake(ponds[side]);if(tries===1)K.say('看看哪片水面叶子更密。','no');else if(tries===2)K.say('对比露出的水面多少。','no');else{busy=true;move(answer);K.say('看，小鱼游到叶多的一边。','no');timer=setTimeout(function(){fish.style.left='546px';fish.style.top='383px';ponds[answer].classList.remove('bloom');busy=false},1600)}}}
ponds.forEach(function(p,i){p.addEventListener('click',function(){choose(i)});p.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(i)}})});
K.drag(fish,{enabled:function(){return K.started&&!busy},targets:function(){return ponds},onTap:function(){selected=true;K.sfx.pick();K.pop(fish);K.say('点一片水面，送小鱼过去')},onDrop:function(el,target){if(target)choose(ponds.indexOf(target));else if(selected)K.say('点一片水面，送小鱼过去')}});
function reset(){clearTimeout(timer);level=0;K.stars=0;K.$('#star-n').textContent='0';draw()}
K.onState=function(state){if(state.demo==='dense'){clearTimeout(timer);level=0;draw();busy=true;move(1);K.say('看，小鱼游到叶多的地方。');}if(state.phase==='play')reset()};
K.onStart=reset;draw();
})();

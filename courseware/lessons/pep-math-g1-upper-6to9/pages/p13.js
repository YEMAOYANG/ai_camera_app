(function(){
var level=0,marks=[],tries=0,busy=false,timer;
K.hud({icon:'●',title:'数到九再停',levels:2});K.owl();K.ready({emoji:'🌲',title:'数到九再停',sub:'数到目标停'});
var spots=[[25,15],[220,40],[420,10],[620,45],[800,15],[100,210],[300,240],[510,205],[720,235]],stones=[];
spots.forEach(function(p,i){var b=K.el('button','stone','<svg viewBox="0 0 150 125"><path class="rock" d="M12 72 Q10 35 47 25 Q80 9 120 33 Q144 50 137 83 Q126 108 76 108 Q27 109 12 88Z" fill="#a9bcc0" stroke="#718f92" stroke-width="5"/><g class="foot" fill="#fff8df"><ellipse cx="74" cy="75" rx="17" ry="23"/><circle cx="57" cy="48" r="6"/><circle cx="70" cy="43" r="6"/><circle cx="83" cy="45" r="5"/><circle cx="94" cy="51" r="4"/></g></svg>',K.$('#stones'));b.id='stone-'+(i+1);b.style.left=p[0]+'px';b.style.top=p[1]+'px';b.setAttribute('aria-label','石子 '+(i+1));b.onclick=function(){if(!K.started||busy)return;var n=marks.indexOf(i);if(n<0){marks.push(i);K.sfx.tick(marks.length)}else{marks.splice(n,1);K.sfx.pick()}render()};stones.push(b)});
function render(){stones.forEach(function(b,i){b.classList.toggle('marked',marks.indexOf(i)>=0)});K.$('#target').textContent=level===0?'6':'9'}
function reset(){clearTimeout(timer);level=0;marks=[];tries=0;busy=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);render();K.say('点石子，数到目标再停')}
K.$('#undo').onclick=function(){if(!K.started||busy)return;marks.pop();render();K.sfx.pick()};
K.$('#stop').onclick=function(){if(!K.started||busy)return;var goal=level===0?6:9;if(marks.length===goal){busy=true;K.sfx.ok();K.star(1,K.$('#stop'));K.say('数对了！','ok');timer=setTimeout(function(){if(level===0){level=1;marks=[];tries=0;busy=false;K.levels(2,1);render();K.say('继续数一数')}else{K.levels(2,2);K.finish({title:'完成啦',sub:'再玩一次',again:reset})}},900)}else{tries++;K.sfx.no();K.shake(K.$('#stop'));if(tries===1)K.say('看看已经留下几个脚印','no');else if(tries===2){K.say('从第一个脚印开始再数一遍','no');K.highlight('#stones')}else{K.say('看，先数三个，再停下来','no');marks=[0,1,2];render();K.highlight('#stop')}}};
K.onState=function(state){if(typeof state.marked==='number'){marks=[];for(var i=0;i<Math.min(9,Math.max(0,state.marked));i++)marks.push(i);render()}if(state.demo){busy=true;marks=[0,1,2];render();K.$('#target').textContent='3';K.highlight('#stop');clearTimeout(timer);timer=setTimeout(function(){busy=false;marks=[];render();K.say('看目标，数一数')},1800)}};
reset();
})();

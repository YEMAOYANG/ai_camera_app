(function(){
if(!K.$('#camp')||!K.$('#flags')||!K.$('#dot-choices'))return;
var tent='<span class="sprite" aria-hidden="true"></span>';
var pos=[[[30,20],[235,20],[440,20],[645,20],[130,240],[340,240],[550,240]],[[130,20],[340,20],[550,20],[30,240],[235,240],[440,240],[645,240]]],level=0,placed=[],tries=0,busy=false,timer,tents=[];
K.hud({icon:'⚑',title:'给七个营地旗',levels:2});K.owl();K.ready({img:'__IMG:forest__',emoji:'🌲',title:'给七个营地旗',sub:'营地插旗',btn:'start-btn'});
for(var i=0;i<7;i++){(function(i){var e=K.el('button','tent',tent+'<span class="badge"></span>',K.$('#camp'));e.id='tent-'+(i+1);e.setAttribute('aria-label','帐篷 '+(i+1));e.addEventListener('click',function(){place(i)});tents.push(e)})(i)}
K.drag(K.$('#flags'),{enabled:function(){return K.started&&!busy},targets:function(){return tents},onDrop:function(el,t){if(t)place(tents.indexOf(t));else miss(el)},onTap:function(){K.say('拖旗子到帐篷，或点帐篷')}});
[6,7].forEach(function(n){var e=K.el('button','choice','',K.$('#dot-choices'));e.id='choice-'+n;e.setAttribute('aria-label',n+'个点');for(var j=0;j<n;j++)K.el('i','dot','',e);e.addEventListener('click',function(){choose(n,e)})});
function render(){tents.forEach(function(e,i){e.style.left=pos[level][i][0]+'px';e.style.top=pos[level][i][1]+'px';var n=placed.indexOf(i);e.classList.toggle('flagged',n>=0);K.$('.badge',e).textContent=n+1})}
function place(i){if(!K.started||busy)return;if(placed.indexOf(i)>=0){miss(tents[i]);return}placed.push(i);render();K.sfx.tick(placed.length);K.say(placed.length===7?'旗子插好了，找同样多的点':'找没有旗的帐篷')}
function miss(e){tries++;K.sfx.no();K.shake(e);if(tries===1)K.say('找没有旗的帐篷','no');else if(tries===2)K.say('一顶帐篷只插一面旗','no');else{placed=[0,1,2,3,4,5,6];render();K.say('一顶插一面，一起数旗子','no')}}
function choose(n,e){if(!K.started||busy)return;if(placed.length===7&&n===7){busy=true;K.sfx.ok();K.star(1,e);K.say('七面旗，七个点','ok');setTimeout(function(){if(level===0){level=1;resetLevel()}else{K.levels(2,2);K.finish({title:'完成啦',sub:'再玩一次',again:restart})}},1000);return}miss(e);if(tries>=3&&placed.length===7)K.highlight('#choice-7')}
function resetLevel(){clearTimeout(timer);placed=[];tries=0;busy=false;K.$('#choice-7').classList.remove('demo');K.levels(2,level);render();K.say('给每顶帐篷插一面旗')}
function restart(){level=0;K.stars=0;K.$('#star-n').textContent='0';resetLevel()}
K.onState=function(state){clearTimeout(timer);busy=false;if(typeof state.placed==='number'){placed=[0,1,2,3,4,5,6].slice(0,Math.max(0,Math.min(7,state.placed)));render()}if(state.demo){placed=[0,1,2,3,4,5,6];render();K.$('#choice-7').classList.add('demo');busy=true;timer=setTimeout(resetLevel,2500)}};
resetLevel();
window.__test=async function(){var R=[],ok=function(n,v){K.check(R,n,v)};K.sim.click(K.$('#start-btn'));for(var i=1;i<=7;i++)K.sim.click(K.$('#tent-'+i));ok('插七面旗',placed.length===7);K.sim.click(K.$('#choice-6'));ok('错选提示',K.$('#say').className==='no');K.sim.click(K.$('#choice-7'));await K.wait(1100);ok('第二关',level===1&&placed.length===0);for(var j=1;j<=7;j++)K.sim.click(K.$('#tent-'+j));K.sim.click(K.$('#choice-7'));await K.wait(1100);ok('完成',!!K.$('#finish:not(.gone)'));K.sim.click(K.$('#btn-again'));ok('重玩',level===0&&placed.length===0&&K.stars===0);K.onState({placed:6});ok('教师插六面',placed.length===6);K.onState({demo:true});ok('教师示范七点',K.$('#choice-7').classList.contains('demo'));clearTimeout(timer);resetLevel();return R};
})();

(function(){
var level=0,station=0,tries=0,busy=false,timer,counts=[1,3,2,4,1,3,4];
K.hud({icon:'▣',title:'数序车站',levels:2});K.owl();K.ready({emoji:'🌲',title:'数序车站',sub:'数序车站'});
var person='<span class="person" aria-hidden="true"></span>';
var stations=[];for(var i=1;i<=7;i++){(function(n){var b=K.el('button','station','<span class="sprite" aria-hidden="true"></span>',K.$('#stations'));b.id='station-'+n;b.setAttribute('aria-label','车站 '+n);b.onclick=function(){move(n)};stations.push(b)})(i)}
[2,3,4,5].forEach(function(n){var b=K.el('button','',String(n),K.$('#numbers'));b.onclick=function(){answer(n,b)}});
function render(){K.$('#goal').textContent='第 '+(level?7:6)+' 站';K.$('#car').style.left=(station?25+(station-1)*172:25)+'px';stations.forEach(function(b,i){b.classList.toggle('chosen',station===i+1)});K.$('#passengers').innerHTML=station?person.repeat(counts[station-1]):''}
function reset(){clearTimeout(timer);level=0;station=0;tries=0;busy=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);render();K.say('从箭头一端找车站')}
function miss(){tries++;K.sfx.no();if(tries===1)K.say('先听清找位置还是数人数','no');else if(tries===2){K.say('从箭头一端逐站数','no');K.highlight('#arrow')}else{busy=true;station=3;render();K.say('看第三站，再数站里的两人','no');timer=setTimeout(function(){busy=false;station=0;tries=0;render()},1800)}}
function move(n){if(!K.started||busy)return;if(n!==(level?7:6)){K.shake(stations[n-1]);miss();return}station=n;render();K.sfx.drop();K.say('数一数站里的乘客')}
function answer(n,b){if(!K.started||busy)return;if(!station||n!==counts[station-1]){K.shake(b);miss();return}busy=true;K.sfx.ok();K.star(1,b);K.say('数对了！','ok');timer=setTimeout(function(){if(!level){level=1;station=0;tries=0;busy=false;K.levels(2,1);render();K.say('再找一个车站')}else{K.levels(2,2);K.finish({title:'完成啦',sub:'再玩一次',again:reset})}},1000)}
K.onState=function(state){if(typeof state.station==='number'){station=Math.max(0,Math.min(7,state.station));render()}if(state.demo){busy=true;station=3;render();clearTimeout(timer);timer=setTimeout(function(){busy=false;station=0;render();K.say('你来找车站')},1800)}};
reset();
})();

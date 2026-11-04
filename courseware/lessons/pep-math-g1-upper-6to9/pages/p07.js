(function(){
var level=0,pairs=[],selected=null,miss=0,timer;
var positions=[[65,35],[235,35],[405,35],[575,35],[745,35],[915,35],[500,225]];
var shellArt='<span class="sprite" aria-hidden="true"></span>';
K.hud({icon:'◉',title:'按二数贝壳',levels:2});K.owl();K.ready({emoji:'🌲',title:'按二数贝壳',sub:'两两数贝壳'});
function render(){var stage=K.$('#groups');stage.innerHTML='<svg class="links" viewBox="0 0 1180 400" aria-hidden="true">'+pairs.map(function(p){var a=positions[p[0]],b=positions[p[1]];return '<line x1="'+(a[0]+65)+'" y1="'+(a[1]+65)+'" x2="'+(b[0]+65)+'" y2="'+(b[1]+65)+'" stroke="#e89b38" stroke-width="8" stroke-linecap="round"/>'}).join('')+'</svg>';var n=level?6:7;for(var i=0;i<n;i++){(function(i){var b=K.el('button','shell',shellArt,stage);b.id='shell-'+(i+1);b.setAttribute('aria-label','贝壳 '+(i+1));b.style.left=positions[i][0]+'px';b.style.top=positions[i][1]+'px';if(pairs.some(function(p){return p.indexOf(i)>=0}))b.classList.add('paired');if(selected===i)b.classList.add('selected');b.onclick=function(){choose(i)};})(i)}K.$('#total').textContent='';}
function reset(){clearTimeout(timer);pairs=[];selected=null;miss=0;render();K.levels(2,level);K.say('两只连成一组，剩下的也数上');}
function choose(i){if(pairs.some(function(p){return p.indexOf(i)>=0})){K.say('这只已经连过了');return}K.sfx.pick();if(selected===i){selected=null}else if(selected===null){selected=i}else{pairs.push([selected,i]);selected=null;K.sfx.tick(pairs.length)}render()}
function wrong(){miss++;K.sfx.no();K.say(miss===1?'看看有没有没连过的贝壳':miss===2?'两只一组，剩下的也要数':'看，先连三组，再数剩下的','no');if(miss>=3){pairs=[[0,1],[2,3],[4,5]];selected=null;render();K.highlight('#groups')}}
K.$('#undo').onclick=function(){if(selected!==null)selected=null;else pairs.pop();render();K.sfx.pick()};
K.$$('#numbers button').forEach(function(b){b.onclick=function(){if(pairs.length<3||+b.dataset.n!==(level?6:7)){wrong();return}K.sfx.ok();K.star(1,b);K.say('数对了','ok');if(level===0){level=1;timer=setTimeout(reset,900)}else{timer=setTimeout(function(){K.finish({title:'完成啦',sub:'再玩一次',again:function(){level=0;K.stars=0;K.$('#star-n').textContent='0';reset()}})},900)}}});
K.onState=function(state){clearTimeout(timer);if(typeof state.pairs==='number'){pairs=[[0,1],[2,3],[4,5]].slice(0,Math.max(0,Math.min(3,state.pairs)));selected=null;render()}if(state.demo){pairs=[[0,1],[2,3],[4,5]];render();K.$('#total').textContent=level?6:7;timer=setTimeout(reset,3000)}};
K.onStart=reset;render();
})();

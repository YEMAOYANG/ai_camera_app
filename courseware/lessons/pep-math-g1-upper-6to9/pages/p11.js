(function(){
if(!K.$('#windmills')||!K.$('#dot-choices')||!K.$('#dots-8')||!K.$('#dots-9')||!K.$('#number-9')||!K.$('#marker'))return;
var level=0,turned=[],miss=0,timer,busy=false;
K.hud({icon:'✿',title:'九个风车',levels:2});K.owl();K.ready({emoji:'🌲',title:'九个风车',sub:'转动风车'});
function pinwheelArt(){return '<span class="sprite" aria-hidden="true"></span>'}
function render(){var board=K.$('#windmills');board.innerHTML='';for(var i=0;i<9;i++){(function(i){var on=turned.indexOf(i)>=0,b=K.el('button','pinwheel'+(on?' turned':''),pinwheelArt(),board);b.id='pinwheel-'+(i+1);b.setAttribute('aria-label','风车 '+(i+1));var col=level?2-i%3:i%3;b.style.left=(65+col*250)+'px';b.style.top=(5+Math.floor(i/3)*175)+'px';b.onclick=function(){if(!K.started||busy)return;if(turned.indexOf(i)>=0){K.say('这只已经转过了');return}turned.push(i);K.sfx.tick(turned.length);render()}})(i)}K.$('#marker').textContent=turned.length?turned.length:''}
function reset(){clearTimeout(timer);turned=[];miss=0;busy=false;K.$('#number-9').style.visibility='hidden';render();K.levels(2,level);K.say('点一点，让每只风车转起来')}
[8,9].forEach(function(n){var b=K.$('#dots-'+n);for(var i=0;i<n;i++)K.el('i','',null,b);b.onclick=function(){if(!K.started||busy)return;if(turned.length!==9||n!==9){miss++;K.sfx.no();K.say(miss===1?'找还没转动的风车':miss===2?'每转一只，就数一个':'看，从第一只转到第九只','no');if(miss>=3){turned=[0,1,2,3,4,5,6,7,8];render();K.highlight('#windmills')}return}busy=true;K.sfx.ok();K.star(1,b);K.$('#number-9').style.visibility='visible';if(level===0){level=1;timer=setTimeout(reset,900)}else{K.levels(2,2);timer=setTimeout(function(){K.finish({title:'完成啦',sub:'再玩一次',again:function(){level=0;K.stars=0;K.$('#star-n').textContent='0';reset()}})},900)}}});
K.onState=function(state){clearTimeout(timer);busy=false;if(typeof state.turned==='number'){turned=Array.from({length:Math.max(0,Math.min(9,state.turned))},function(_,i){return i});render()}if(state.demo){busy=true;turned=[0,1,2,3,4,5,6,7,8];render();K.$('#number-9').style.visibility='visible';K.highlight('#dots-9');timer=setTimeout(reset,3000)}};
K.onStart=reset;render();
})();

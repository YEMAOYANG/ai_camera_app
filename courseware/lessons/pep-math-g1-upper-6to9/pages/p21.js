(function(){
if(!K.$('#objects')||!K.$('#baskets'))return;
var round=0,marked=[],misses=0,busy=false,demoMode=false,timer,counts=[6,7,8,9];K.hud({icon:'●',title:'整理观察记录',levels:2});K.owl();
function objectArt(){return '<span class="sprite" aria-hidden="true"></span>'}
function basket(n){return '<b>'+n+'</b>'}
function draw(){var box=K.$('#objects');box.innerHTML='';var total=demoMode?6:counts[round];for(var i=0;i<total;i++){(function(i){var kind=demoMode?0:round,o=K.el('button','object kind-'+kind,objectArt(),box);o.setAttribute('aria-label','物品 '+(i+1));var n=marked.indexOf(i);if(n>=0)K.el('span','count',String(n+1),o);o.addEventListener('click',function(e){e.stopPropagation();if(busy)return;if(marked.indexOf(i)<0){marked.push(i);K.sfx.tick(marked.length);draw()}})})(i)}var baskets=K.$('#baskets');baskets.innerHTML='';counts.forEach(function(n){var b=K.el('div','basket',basket(n),baskets);b.id='basket-'+n})}
K.drag(K.$('#objects'),{targets:function(){return K.$$('.basket')},onDrop:function(el,t){if(busy)return;if(marked.length!==counts[round]||!t||+t.id.slice(7)!==counts[round]){misses++;K.sfx.no();K.say(misses===1?'先数这组物品':misses===2?'两两或三三数，剩下的也数':'看六件物品怎样放进篮子','no');if(misses>=3)demo();return}busy=true;K.sfx.ok();K.star(1,t);t.style.filter='drop-shadow(0 0 10px #58B45C)';setTimeout(function(){round++;marked=[];misses=0;busy=false;if(round===4){K.finish({title:'完成啦',sub:'再玩一次',again:reset});return}K.levels(2,round>=2?1:0);draw()},800)}});
function demo(){busy=true;demoMode=true;marked=[0,1,2,3,4,5];draw();var target=K.$('#basket-6');if(target)target.style.filter='drop-shadow(0 0 10px #58B45C)';clearTimeout(timer);timer=setTimeout(function(){demoMode=false;marked=[];busy=false;draw()},1800)}
function reset(){clearTimeout(timer);round=0;marked=[];misses=0;busy=false;demoMode=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);draw();K.say('数一数，把这一组送到篮子里')}
K.onState=function(state){clearTimeout(timer);demoMode=false;busy=false;if(state.marked!==undefined){marked=[];for(var i=0;i<Math.min(counts[round],state.marked);i++)marked.push(i);draw()}if(state.demo)demo()};K.ready({emoji:'🌲',title:'整理观察记录',sub:'整理观察记录'});reset();
})();

(function(){
var tasks=[[3,5],[5,4],[7,2]],level=0,a=3,b=5,moved=[false,false],swapped=false,solved=false,demo=false,busy=false,miss=0,timer;
K.hud({icon:'◉',title:'两组接成一排',levels:3});K.owl();K.ready({emoji:'◉',title:'两组接成一排',sub:'拖两组到长托盘，再点整体数量图'});
function counter(parent){var e=K.el('span','counter','<img src="__IMG:counter__" alt="">',parent);e.querySelector('img').onerror=function(){this.style.visibility='hidden';e.classList.add('fallback')}}
function group(parent,n,cls){var g=K.el('div','group'+(cls?' second':''),'',parent);for(var i=0;i<n;i++)counter(g)}
function render(){[a,b].forEach(function(n,s){var p=K.$(s?'#part-b':'#part-a');p.innerHTML='';p.classList.toggle('placed',moved[s]);if(!moved[s])for(var i=0;i<n;i++)counter(p)});var z=K.$('#merge-zone');z.innerHTML='';var order=swapped?[1,0]:[0,1];order.forEach(function(s){if(moved[s])group(z,s?b:a,s)});K.$('#merge-equation').textContent=(swapped?b:a)+' + '+(swapped?a:b)+' = '+(solved||(demo&&moved[0]&&moved[1])?a+b:'?');K.levels(3,level)}
function options(){var p=K.$('#merge-options');p.innerHTML='';K.shuffle([a+b-1,a+b,a+b===9?7:9]).forEach(function(n){var e=K.el('button','answer','<span class="quantity">'+Array(n+1).join('<i></i>')+'</span>',p);e.setAttribute('aria-label',n+'个数量点');e.onclick=function(){check(n,e)}})}
function load(){a=tasks[level][0];b=tasks[level][1];moved=[false,false];swapped=false;solved=false;busy=false;miss=0;render();options();K.say('把两个部分都合到长托盘，再找整体。')}
function reset(){clearTimeout(timer);level=0;demo=false;K.stars=0;K.$('#star-n').textContent='0';load()}
function move(s){if(demo||busy||moved[s])return;moved[s]=true;render();K.sfx.drop();K.say(moved[0]&&moved[1]?'两个部分都来了，点表示整体的数量图。':'还有一个部分，别漏掉。')}
[0,1].forEach(function(s){var e=K.$(s?'#part-b':'#part-a');K.drag(e,{enabled:function(){return !demo&&!busy&&!moved[s]},targets:function(){return [K.$('#merge-zone')]},onDrop:function(el,t){if(t)move(s)},onTap:function(){move(s)}})});
K.$('#swap-groups').onclick=function(){if(!demo&&!busy){swapped=!swapped;render();K.sfx.pick();K.say('两组先后交换，物品没有增加或减少。')}};
function check(n,e){if(demo||busy)return;if(!moved[0]||!moved[1]||n!==a+b){miss++;K.sfx.no();K.shake(e);K.say(miss===1?'先看看两部分有没有全到，再数整体。':miss===2?'一个部分也不能漏，数一数全部圆片。':'我们把两部分都移进来，再慢慢数。','no');if(miss>=3){moved=[true,true];render();K.highlight('#merge-zone');miss=0}return}busy=true;solved=true;render();K.star(1,e);K.sfx.ok();K.say('两部分合在一起，就是整体数量。','ok');timer=setTimeout(function(){level++;if(level===tasks.length)K.finish({title:'两部分合成整体',sub:'先后可以交换，整体数量不变。',again:reset});else load()},950)}
K.onStart=reset;K.onState=function(state){clearTimeout(timer);if(state.demo){demo=true;a=3;b=5;moved=[false,false];swapped=false;solved=false;render();options()}if(state.demoMerged){demo=true;moved=[true,true];render()}if(state.demoSwap){demo=true;swapped=true;render()}if(state.play)reset()};load();
})();

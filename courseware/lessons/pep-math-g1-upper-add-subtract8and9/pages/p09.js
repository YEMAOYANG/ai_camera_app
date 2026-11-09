(function(){
var tasks=[[3,5],[7,2],[5,4]],level=0,a=3,b=5,demo=false,revealed=false,busy=false,miss=0,timer;
K.hud({icon:'◉',title:'盖着的部分有多少',levels:3});K.owl();K.ready({emoji:'◉',title:'盖着的部分有多少',sub:'想已知的加法，找出盖板下的部分'});
function draw(n,parent){parent.innerHTML='';for(var i=0;i<n;i++){var e=K.el('span','counter','<img src="__IMG:counter__" alt="">',parent);e.querySelector('img').onerror=function(){this.style.visibility='hidden';this.parentElement.classList.add('fallback')}}}
function render(){K.$('#known-add').textContent=a+' + '+b+' = '+(a+b);draw(a,K.$('#visible-part'));draw(b,K.$('#hidden-counters'));K.$('#hidden-part').classList.toggle('revealed',revealed);K.$('#missing-equation').textContent=(a+b)+' − '+a+' = '+(revealed?b:'?');K.levels(3,level)}
function options(){var p=K.$('#hidden-options');p.innerHTML='';K.shuffle([b,b-1,b+1]).forEach(function(n){var e=K.el('button','answer','<span class="quantity">'+Array(n+1).join('<i></i>')+'</span>',p);e.setAttribute('aria-label',n+'个数量点');e.onclick=function(){choose(n,e)}})}
function load(){a=tasks[level][0];b=tasks[level][1];revealed=false;busy=false;miss=0;render();options();K.say('看见一部分，想已知加法，找盖住的部分。')}
function reset(){clearTimeout(timer);level=0;demo=false;K.stars=0;K.$('#star-n').textContent='0';load()}
function choose(n,e){if(demo||busy)return;if(n!==b){miss++;K.sfx.no();K.shake(e);K.say(miss===1?'先认整体和看得见的部分，再想另一个。':miss===2?'已知加法里，哪两个部分合成这个整体？':'对照加法的两个部分，再把它们加回去。','no');if(miss>=3){K.highlight('#known-add');miss=0}return}revealed=true;busy=true;render();K.star(1,e);K.sfx.ok();K.say('移开盖板核对，两部分确实合成这个整体。','ok');timer=setTimeout(function(){level++;if(level===tasks.length)K.finish({title:'想加算减有依据',sub:'知道两部分合起来，就能找另一部分。',again:reset});else load()},1100)}
K.onStart=reset;K.onState=function(state){clearTimeout(timer);if(state.demo){demo=true;a=4;b=5;revealed=false;render();options()}if(state.demoReveal){demo=true;revealed=true;render()}if(state.play)reset()};load();
})();

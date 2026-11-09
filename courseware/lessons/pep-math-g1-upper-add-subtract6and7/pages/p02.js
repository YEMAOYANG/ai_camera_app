(function(){
var tasks=[[2,4],[1,6],[5,2]],level=0,a=2,b=4,joined=[false,false],demo=false,demoSolved=false,busy=false,miss=0,timer;
K.hud({icon:'◉',title:'两组合到一起',levels:3});K.owl();K.ready({emoji:'◉',title:'两组合到一起',sub:'把两组都拖入中间，再选总数'});
function beads(parent,n,cls){for(var i=0;i<n;i++){var e=K.el('span','bead'+(cls?' '+cls:''),'<img src="__IMG:bead__" alt="">',parent);e.querySelector('img').onerror=function(){this.style.visibility='hidden';this.parentElement.classList.add('fallback')}}}
function dots(parent,n){for(var i=0;i<n;i++)K.el('i','','',parent)}
function render(){[0,1].forEach(function(s){var p=K.$(s?'#part-b':'#part-a');p.innerHTML='';p.classList.toggle('joined',joined[s]);beads(p,s?b:a);p.setAttribute('aria-label',(s?'右边':'左边')+(s?b:a)+'片')});var zone=K.$('#merge-zone');zone.innerHTML='';if(joined[0])beads(zone,a,'from-a');if(joined[1])beads(zone,b,'from-b');K.$('#equation').textContent=a+' + '+b+' = '+(demo&&demoSolved?a+b:'?');var answers=K.$('#answer-options');answers.innerHTML='';K.shuffle([a+b,a+b-1,a+b+1]).forEach(function(n,i){var e=K.el('button','answer quantity','',answers);e.id='answer-'+(i+1);e.setAttribute('aria-label',n+'个数量点');dots(e,n);e.disabled=demo||busy;e.onclick=function(){choose(n)}});K.levels(3,level)}
function load(){a=tasks[level][0];b=tasks[level][1];joined=[false,false];miss=0;busy=false;render();K.say('两组都合起来，再找一共有多少片。')}
function reset(){clearTimeout(timer);level=0;demo=false;demoSolved=false;K.stars=0;K.$('#star-n').textContent='0';load()}
function merge(s){if(demo||busy||joined[s])return;joined[s]=true;render();K.sfx.drop()}
[0,1].forEach(function(s){K.drag(K.$(s?'#part-b':'#part-a'),{enabled:function(){return !demo&&!busy&&!joined[s]},targets:function(){return [K.$('#merge-zone')]},onDrop:function(el,target){if(target)merge(s)},onTap:function(){merge(s)}})});
K.$('#swap-parts').onclick=function(){if(demo||busy)return;var t=a;a=b;b=t;joined=[false,false];render();K.say('两个部分换位置，总数不会变。')};
function choose(n){if(demo||busy)return;if(!joined[0]||!joined[1]||n!==a+b){miss++;K.sfx.no();K.say(miss===1?'两组都合好了吗？把每一片都数上。':miss===2?'可以想这两个部分组成多少。':'先把两组合起来，再从第一片数到最后。','no');if(miss>=3){K.highlight('#merge-zone');miss=0}return}busy=true;K.$('#equation').textContent=a+' + '+b+' = '+n;K.star(1,K.$('#merge-zone'));K.sfx.ok();K.say('两个部分合起来，加法求的是整体。','ok');timer=setTimeout(function(){level++;if(level===tasks.length)K.finish({title:'两部分合成了整体',sub:'交换两个加数，结果还是相同。',again:reset});else load()},950)}
K.onStart=reset;K.onState=function(state){clearTimeout(timer);if(state.demo){demo=true;demoSolved=false;a=2;b=4;joined=[false,false];render();K.say('老师先摆两片和四片，再合到一起。')}if(state.demoMerged){demo=true;joined=[true,true];render()}if(state.demoSolved){demoSolved=true;render()}if(state.play)reset()};load();
})();

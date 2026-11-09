(function(){
var positions=[null,null,null],selected=null,misses=0,busy=false,demo=false,timer;
var entries=['try','observe','guess'];
K.hud({icon:'◎',title:'科学活动排顺序',levels:1});K.owl();K.ready({emoji:'◎',title:'科学活动排顺序',sub:'先想一想，再试一试、看一看'});
function bindCards(){K.$$('.step-card').forEach(function(card){card.addEventListener('click',function(e){e.stopPropagation();pick(card)});K.drag(card,{enabled:function(){return K.started&&!busy&&!demo},targets:function(){return K.$$('.step-slot')},onTap:function(){pick(card)},onDrop:function(el,target){if(target)place(el.dataset.step,Number(target.dataset.slot))}})})}
function render(){K.$$('.step-slot').forEach(function(slot,i){slot.classList.toggle('success',busy&&!demo);if(positions[i])slot.appendChild(K.$('#step-card-'+positions[i]))});entries.forEach(function(key){var card=K.$('#step-card-'+key);if(positions.indexOf(key)<0)K.$('#steps-tray').appendChild(card);card.classList.toggle('selected',key===selected)});K.levels(1,busy&&!demo?1:0)}
function reset(){clearTimeout(timer);positions=[null,null,null];selected=null;misses=0;busy=false;demo=false;K.stars=0;K.$('#star-n').textContent='0';render();K.say('先选图卡，再选位置；也可以拖一拖。')}
function pick(card){if(!K.started||busy||demo)return;selected=card.dataset.step;render();K.sfx.pick()}
function place(key,index){if(!key||busy||demo)return;var previous=positions.indexOf(key),other=positions[index];if(previous>=0)positions[previous]=other;positions[index]=key;selected=null;render();K.sfx.drop()}
K.$$('.step-slot').forEach(function(slot){function act(){if(selected)place(selected,Number(slot.dataset.slot))};slot.addEventListener('click',act);slot.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();act()}})});
K.$('#check-sequence').addEventListener('click',function(){if(!K.started||busy||demo)return;if(positions.join(',')!=='guess,try,observe'){misses++;K.sfx.no();K.say(misses===1?'看看每张图，活动发生在什么时候？':misses===2?'分清还没动手、正在尝试和观察发现。':'先想动手前的事，再看后来的事。','no');if(misses>=3){K.highlight('#step-slots');misses=0}return}busy=true;render();K.star(3,K.$('#check-sequence'));K.sfx.ok();K.say('先猜，再尝试，接着观察和交流。','ok');timer=setTimeout(function(){K.finish({title:'顺序排好了',sub:'实际活动也要留心观察。',again:reset})},950)});
K.onStart=reset;K.onState=function(state){if(state.demo==='first'){reset();positions[0]='guess';render();demo=true;K.say('动手之前先猜，放在第一位。','ok')}if(state.phase==='play')reset()};bindCards();render();
K.$('#play').addEventListener('error',function(e){if(e.target&&e.target.tagName==='IMG'){e.target.alt='图片暂未加载';K.say('图片暂未加载，请重新打开这一页。','no')}},true);
})();
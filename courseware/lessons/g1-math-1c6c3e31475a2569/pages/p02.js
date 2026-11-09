(function(){
var assets={book:'__IMG:book__',tree:'__IMG:tree__',ball:'__IMG:ball__'};
/* CUE_MAP */ var cues={"card-book":"/api/classroom-media/__STAGE__/media/tts-p02-12-fdf5f88c1cc99d5a0fd9ae833b5b107e14ce64474646d27e6aebb0bd9bf0fcdf.wav","card-tree":"/api/classroom-media/__STAGE__/media/tts-p02-13-5e125890caae52ad0db52ed862902d5f69e2759da6a74c57216da7f34622cce7.wav","card-ball":"/api/classroom-media/__STAGE__/media/tts-p02-14-30faf90f1570cf67c8ab2e5d43032ed35254fcfcb21aff271b75442e0a680459.wav"};
var tasks=[{key:'book',count:3,context:'名片图卡',cue:'card-book'},{key:'tree',count:5,context:'校园图卡',cue:'card-tree'},{key:'ball',count:4,context:'玩具图卡',cue:'card-ball'}];
var level=0,miss=0,locked=false,demo=false,timer=null,epoch=0,audio=null;
K.hud({icon:'◌',title:'听数量，做图卡',levels:3});K.owl();K.ready({emoji:'◌',title:'听数量，做图卡',sub:'听一听，再把合适的图片放进图卡'});
function stopAudio(){if(audio){audio.pause();audio=null}}
function speak(){stopAudio();var url=cues[tasks[level].cue];if(!url)return;audio=new Audio(url);audio.play().catch(function(){K.say('请再点一次听题。')})}
function unit(parent,key){var im=K.el('img','garden-unit','',parent);im.src=assets[key];im.alt={book:'一本绘本',tree:'一棵小树',ball:'一个小球'}[key];im.onerror=function(){parent.classList.add('garden-image-failed');K.say('图片还没加载好，请点重载图片。','no')};return im}
function group(parent,key,count){var g=K.el('div','garden-group','',parent);for(var i=0;i<count;i++)unit(g,key);return g}
function board(key,count){var b=K.$('#garden-board');b.innerHTML='';if(count)for(var i=0;i<count;i++)unit(b,key);else K.el('span','garden-caption','把选好的整组图片放到这里',b)}
function render(){var t=demo?{key:'book',count:2,context:'老师示范'}:tasks[level];K.$('#garden-context').textContent=t.context;K.$('#garden-options').innerHTML='';var counts=demo?[1,2,3]:K.shuffle([t.count-1,t.count,t.count+1]);counts.forEach(function(n){var b=K.el('button','garden-choice','',K.$('#garden-options'));b.setAttribute('aria-label',n+'件物品');b.dataset.count=String(n);group(b,t.key,n);b.addEventListener('click',function(){choose(n,b)})});K.levels(3,level)}
function load(){miss=0;locked=false;board('',0);render();K.say(tasks[level].context+'：听数量，再选整组图片。')}
function reset(){epoch++;clearTimeout(timer);stopAudio();level=0;miss=0;demo=false;locked=false;K.stars=0;K.$('#star-n').textContent='0';load()}
function hint(){if(demo||locked)return;miss++;K.say(miss===1?'先听清要数什么，再一件一件指着数。':miss===2?'每件只数一次，数过的不要再数。':'分成一排从头数，看看有没有漏掉。');if(miss>2)K.highlight('#garden-options')}
function choose(n,b){if(demo||locked)return;var t=tasks[level];if(b.querySelector('.garden-image-failed')){K.say('先把图片重载好，再选。','no');return}if(n!==t.count){b.classList.add('wrong');K.shake(b);K.sfx.no();hint();return}locked=true;stopAudio();board(t.key,n);K.star(1);K.sfx.ok();K.say('对象和数量都放对了。可以说给大人听。','ok');var stamp=epoch;timer=setTimeout(function(){if(stamp!==epoch)return;level++;if(level===tasks.length){K.finish({title:'数量图卡做好了',sub:'记录了选择与数量，口头介绍请大人观察。',again:reset})}else{load();speak()}},1000)}
K.$('#garden-listen').addEventListener('click',function(){if(!demo&&!locked)speak()});K.$('#garden-help').addEventListener('click',hint);K.$('#garden-reload').addEventListener('click',function(){K.$$('img.garden-unit').forEach(function(im){im.parentNode.classList.remove('garden-image-failed');im.src=im.src})});
K.onStart=reset;K.onState=function(state){epoch++;clearTimeout(timer);stopAudio();if(state.demo){demo=true;locked=true;level=0;board('',0);render()}if(state.demoPlaced){demo=true;board('book',2)}if(state.play){reset();speak()}};load();
})();

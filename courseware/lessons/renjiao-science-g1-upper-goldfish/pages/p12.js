(function(){
var scenes=['__IMG:tap__','__IMG:grab__'],level=0,tries=0,busy=false,phase='play',epoch=0,photo=K.$('#care-scene'),record=K.$('#care-record');
var picturesReady=false,pictureLoad=0,pictures=['__IMG:tap__','__IMG:grab__','__IMG:station__'];
var retry=K.$('#care-reset');
function loadPictures(){
  picturesReady=false;
  retry.hidden=true;
  var token=++pictureLoad,left=pictures.length;
  pictures.forEach(function(src){
    var im=new Image();
    im.onload=function(){if(token===pictureLoad&&--left===0)picturesReady=true};
    im.onerror=function(){
      if(token!==pictureLoad)return;
      retry.hidden=false;
      K.say('图片暂未载入，请点重来或重新打开本页');
    };
    im.src=src;
  });
}
K.hud({icon:'◉',title:'给观察站换个做法',levels:2});K.owl();K.ready({emoji:'◉',title:'给观察站换个做法',sub:'看动作，换一种做法',btn:'start-btn'});
function scene(){photo.style.backgroundImage='url("'+scenes[level]+'")';photo.classList.remove('safe');K.levels(2,level);tries=0;busy=false;var choices=K.$('#care-choices');K.shuffle(Array.from(choices.children)).forEach(function(el){choices.appendChild(el)});K.say(level===0?'看看手在做什么，换成合适的观察动作':'换了一个情境，再选合适的观察动作')}
function reset(){epoch++;phase='play';level=0;record.innerHTML='';K.stars=0;K.$('#star-n').textContent='0';scene();loadPictures()}
function answer(kind,el){if(!K.started||phase!=='play'||busy)return;if(!picturesReady){K.say('图片正在加载，稍等或点重来再试');return}if(kind!=='quiet'){tries++;K.sfx.no();K.shake(el);if(tries===1)K.say('再看看人物的手，想想这样合适吗','no');else if(tries===2)K.say('观察要安静，金鱼留在水里','no');else{K.highlight('#care-choice-quiet');K.say('老师指出合适的动作，再由你换上','no')}return}
busy=true;photo.style.backgroundImage='url("__IMG:station__")';photo.classList.add('safe');var im=K.el('img','',null,record);im.src='__IMG:station__';im.alt='改为在鱼缸外安静观察并记录';K.sfx.ok();K.star(1,el);K.say('换好了，人和记录本留在鱼缸外','ok');var id=epoch;setTimeout(function(){if(id!==epoch)return;if(level===1){K.levels(2,2);K.finish({title:'观察站准备好了',sub:'安静、不拍缸、不触摸金鱼',again:reset})}else{level++;scene()}},850)}
K.$$('#care-choices button').forEach(function(b){b.addEventListener('click',function(){answer(b.dataset.kind,b)})});retry.addEventListener('click',loadPictures);
K.onState=function(state){if(state.demo==='quiet'){phase='demo';photo.style.backgroundImage='url("__IMG:station__")';photo.classList.add('safe');record.innerHTML='';var im=K.el('img','',null,record);im.src='__IMG:station__';im.alt='老师示范安静观察的做法'}if(state.phase==='play')reset()};K.onStart=reset;reset();
})();

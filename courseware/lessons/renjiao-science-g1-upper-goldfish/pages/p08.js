(function(){
var tasks=['tail','fin','body'],sources={tail:'__IMG:tail__',fin:'__IMG:fin__',body:'__IMG:fish-orange__'},level=0,selected=null,tries=0,busy=false,phase='play',epoch=0,paused=true;
var tank=K.$('#motion-tank'),fish=K.$('#motion-fish'),record=K.$('#motion-record');
var toggle=K.$('#motion-toggle'),camera=K.$('#motion-camera'),retry=K.$('#motion-reset');
var choices=K.$$('#motion-parts button');
var picturesReady=false,pictureLoad=0;
function loadPictures(){
  picturesReady=false;
  retry.hidden=true;
  var token=++pictureLoad,left=tasks.length;
  tasks.forEach(function(part){
    var im=new Image();
    im.onload=function(){if(token===pictureLoad&&--left===0)picturesReady=true};
    im.onerror=function(){
      if(token!==pictureLoad)return;
      retry.hidden=false;
      K.say('图片暂未载入，请点重来或重新打开本页');
    };
    im.src=sources[part];
  });
}
K.hud({icon:'◉',title:'观察变化，留下证据',levels:3});K.owl();K.ready({emoji:'◉',title:'观察变化，留下证据',sub:'播放、看变化，再拍观察卡',btn:'start-btn'});
function mode(part){tank.classList.remove('show-tail','show-fin','show-body');tank.classList.add('show-'+part)}
function setPaused(value){
  paused=value;
  tank.classList.toggle('paused',paused);
  toggle.textContent=paused?'▶':'Ⅱ';
  toggle.setAttribute('aria-label',paused?'播放示意':'暂停示意');
}
function prepare(){
  selected=null;
  tries=0;
  busy=false;
  setPaused(true);
  camera.disabled=true;
  toggle.disabled=false;
  choices.forEach(function(button){
    button.disabled=true;
    button.classList.remove('selected');
  });
  mode(tasks[level]);
  fish.style.left=(100+level*60)+'px';
  fish.style.top=(level===1?50:75)+'px';
  K.levels(3,level);
  K.say('先播放，看哪一处在变化，再选图片，点相机');
}
function reset(){epoch++;phase='play';level=0;record.innerHTML='';K.stars=0;K.$('#star-n').textContent='0';prepare();loadPictures()}
function choose(part,button){
  if(!K.started||busy||phase!=='play'||button.disabled)return;
  selected=part;
  camera.disabled=false;
  choices.forEach(function(choice){choice.classList.toggle('selected',choice===button)});
  K.sfx.pick();
}
function addRecord(part,alt){
  var image=K.el('img','',null,record);
  image.src=sources[part];
  image.alt=alt;
}
function capture(){
  if(!K.started||busy||phase!=='play'||!selected)return;
  if(!picturesReady){K.say('图片正在加载，稍等或点重来再试');return}
  if(selected!==tasks[level]){
    tries++;
    K.sfx.no();
    if(tries===1)K.say('再看看动画，找到正在变化的地方','no');
    else if(tries===2){setPaused(false);K.say('慢慢看那一处，再选一张近景','no')}
    else{K.highlight('#motion-'+tasks[level]+'-choice');K.say('老师指一下部位，再由你留下记录','no')}
    return;
  }
  busy=true;
  camera.disabled=true;
  addRecord(selected,'屏幕示意中的观察部位');
  K.sfx.ok();
  K.star(1,camera);
  K.say('记录了这次示意的变化，继续留心其他部位','ok');
  var id=epoch;
  setTimeout(function(){
    if(id!==epoch)return;
    if(level===2){
      K.levels(3,3);
      K.finish({title:'三条线索记好了',sub:'示意帮助理解，真实鱼还要继续观察',again:reset});
    }else{
      level++;
      prepare();
    }
  },800);
}
choices.forEach(function(button){button.addEventListener('click',function(){choose(button.dataset.part,button)})});
camera.addEventListener('click',capture);
toggle.addEventListener('click',function(){
  if(!K.started||phase!=='play'||busy)return;
  setPaused(!paused);
  if(!paused)choices.forEach(function(button){button.disabled=false});
});
retry.addEventListener('click',loadPictures);
K.onState=function(state){
  if(state.demo){
    phase='demo';
    toggle.disabled=true;
    if(state.demo==='record-tail'){
      setPaused(true);
      if(!record.firstChild)addRecord('tail','老师记录的尾部示意');
      K.highlight('#motion-camera');
      return;
    }
    mode(state.demo);
    setPaused(false);
    fish.style.left='150px';
    fish.style.top='75px';
    K.say('老师演示动画中的部位，不是真实实验');
  }
  if(state.phase==='play')reset();
};K.onStart=reset;reset();
})();

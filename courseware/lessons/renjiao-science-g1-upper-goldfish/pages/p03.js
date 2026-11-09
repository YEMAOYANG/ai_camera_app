(function(){
var steps=['whole','head','body','tail'],pictures=['__IMG:fish-orange__','__IMG:fish-red__'],level=0,step=0,tries=0,busy=false,phase='play',epoch=0;
var photo=K.$('#observe-photo'),strip=K.$('#observe-strip'),glass=K.$('#observe-glass'),retry=K.$('#observe-reset');
var picturesReady=false,pictureLoad=0;
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
K.hud({icon:'◉',title:'让放大镜走一遍',levels:2});K.owl();K.ready({emoji:'◉',title:'让放大镜走一遍',sub:'听老师说，按顺序观察',btn:'start-btn'});
function style(el,kind){el.style.backgroundImage='url("'+pictures[level]+'")';el.style.backgroundSize=kind==='whole'?'contain':kind==='head'?'250% auto':'230% auto';el.style.backgroundPosition=kind==='head'?'8% 50%':kind==='tail'?'95% 50%':'center'}
function view(kind){
  style(photo,kind);
  glass.style.opacity=kind==='whole'?'0':'1';
  glass.style.left=({head:225,body:315,tail:356}[kind]||225)+'px';
}
function recordObservation(kind){
  var record=K.el('div','observe-record',null,strip);
  style(record,kind);
}
function reset(){epoch++;level=0;step=0;tries=0;phase='play';busy=false;K.stars=0;K.$('#star-n').textContent='0';strip.innerHTML='';K.levels(2,0);view('whole');refresh();loadPictures();K.say('先听老师的观察方法，再按顺序点图片')}
function refresh(){K.$$('#observe-choices .view').forEach(function(el){el.style.backgroundImage='url("'+pictures[level]+'")'})}
function choose(kind,button){if(!K.started||busy||phase!=='play')return;if(!picturesReady){K.say('图片正在加载，稍等或点重来再试');return}if(kind!==steps[step]){tries++;K.sfx.no();K.shake(button);if(tries===1)K.say('再想一想，观察要有怎样的先后顺序','no');else if(tries===2)K.say('先看整体，再从头往后看','no');else{view(steps[step]);K.say('老师示范这一处，再由你点一次','no')}return}
tries=0;view(kind);recordObservation(kind);K.sfx.ok();K.star(1,button);step++;K.say('看到这一处，把它留下作观察记录','ok');if(step<4)return;busy=true;var id=epoch;setTimeout(function(){if(id!==epoch)return;if(level===1){K.levels(2,2);K.finish({title:'观察记录完成',sub:'先整体，再从头看到尾',again:reset});return}level++;step=0;strip.innerHTML='';busy=false;refresh();view('whole');K.levels(2,level);K.say('换一条金鱼，也按同样顺序观察')},850)}
K.$$('#observe-choices button').forEach(function(button){button.addEventListener('click',function(){choose(button.dataset.view,button)})});retry.addEventListener('click',loadPictures);
function demonstrate(kind){
  phase='demo';
  view(kind);
  strip.innerHTML='';
  steps.slice(0,steps.indexOf(kind)+1).forEach(recordObservation);
}
K.onState=function(state){
  if(state.demo==='rest'){
    demonstrate('body');
    K.highlight('#observe-strip');
    var id=epoch;
    setTimeout(function(){
      if(id===epoch&&phase==='demo')demonstrate('tail');
    },1050);
  }else if(state.demo){
    demonstrate(state.demo);
  }
  if(state.phase==='play')reset();
};K.onStart=reset;reset();
})();

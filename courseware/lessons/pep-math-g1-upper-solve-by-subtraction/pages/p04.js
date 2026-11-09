(function(){
  var crossed=new Set(),phase=0,demo=false,mistakes=0,timer=null,version=0;
  K.hud({title:'画点表示减法',icon:'−',levels:2});K.owl();
  for(var i=0;i<5;i++){var picture=K.el('div','p04-picture','<img src="__IMG:toy-car__" alt="一辆小车"><i data-semantic-diagram="图片失败时一辆车对应一个点"></i>',K.$('#p04-cars'));K.$('img',picture).addEventListener('error',function(){this.parentElement.classList.add('failed')})}
  function render(){
    K.$('#p04-marks').innerHTML='';
    for(var j=0;j<5;j++)(function(n){var b=K.el('button','p04-mark'+(crossed.has(n)?' marked':''),'<i></i>',K.$('#p04-marks'));b.id='p04-mark-'+n;b.setAttribute('aria-label','第'+(n+1)+'个数量点'+(crossed.has(n)?'已划去':''));b.disabled=demo||phase!==0||crossed.has(n);b.onclick=function(){if(b.disabled)return;crossed.add(n);K.sfx.pick();if(crossed.size===2){phase=1;K.levels(2,1);K.say('两辆已发出。选出没有划去的数量。')}else K.say('一条斜线，表示移走一辆。');render()}})(j);
    K.$('#p04-choices').classList.toggle('hide',demo||phase!==1);
  }
  function reset(){clearTimeout(timer);version++;crossed=new Set();phase=0;demo=false;mistakes=0;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);K.$$('.p04-choice').forEach(function(x){x.disabled=false});render();K.say('点两个数量点，给发出的两辆做记号。')}
  [3,1,4].forEach(function(n){var b=K.el('button','p04-choice',Array.from({length:n},function(){return '<i></i>'}).join(''),K.$('#p04-choices'));b.id='p04-answer-'+n;b.setAttribute('aria-label',n+'个数量点');b.onclick=function(){if(demo||phase!==1)return;if(n!==3){mistakes++;K.sfx.no();K.shake(b);K.highlight('#p04-marks');K.say(mistakes===1?'没划去的点才表示剩余，再看看。':'用手指逐个数没划线的点，别重复。','no');return}phase=2;K.levels(2,2);K.star(1,b);K.say('点和小车一一对应，找到了剩余。','ok');K.sfx.ok();K.$$('.p04-choice').forEach(function(x){x.disabled=true});var token=version;timer=setTimeout(function(){if(token!==version)return;K.finish({title:'数量点帮上忙',sub:'划去表示去掉，没划去表示留下',again:reset})},700)}});
  K.onStart=reset;K.onState=function(s){if(s.resetTask)reset();if(typeof s.demoCross==='number'){reset();demo=true;for(var i=0;i<Math.min(s.demoCross,2);i++)crossed.add(i);render();K.say('教师示范：划去两个，观察没有划去的点。')}};
  reset();K.ready({title:'画点找剩余',sub:'一辆车一个点，发出就划去',emoji:'−'});
})();

(function(){
  var moved=new Set(),phase=0,mistakes=0,demo=false,timer=null,version=0;
  K.hud({title:'整体里找剩余',icon:'−',levels:3});K.owl();
  function fallback(img){img.addEventListener('error',function(){img.parentElement.classList.add('failed')})}
  function dots(n){return Array.from({length:n},function(){return '<i></i>'}).join('')}
  function car(i){
    var b=K.el('button','p02-car'+(moved.has(i)?' placed':''),'<img src="__IMG:toy-car__" alt="一辆玩具小车"><span class="p02-fallback" data-semantic-diagram="图片失败时用一个数量点表示一辆车"></span>');
    b.id='p02-car-'+i;b.setAttribute('aria-label','第'+(i+1)+'辆小车');b.disabled=demo||phase!==1||moved.has(i);fallback(K.$('img',b));
    function transfer(){if(b.disabled)return;moved.add(i);K.sfx.pick();if(moved.size===3){phase=2;K.levels(3,2);K.say('已发出三辆。选图表示留下的数量。')}else K.say('继续把任务中的小车移到右边。');render()}
    K.drag(b,{enabled:function(){return !b.disabled},targets:function(){return [K.$('#p02-dispatch')]},onTap:transfer,onDrop:function(el,target){if(target)transfer();else{K.say('请把小车放进右边出发区。','no');K.shake(el)}}});return b
  }
  function render(){
    K.drags=[];K.$('#p02-stock-cars').innerHTML='';K.$('#p02-dispatch-cars').innerHTML='';
    for(var i=0;i<7;i++)(moved.has(i)?K.$('#p02-dispatch-cars'):K.$('#p02-stock-cars')).appendChild(car(i));
    K.$('#p02-whole').disabled=demo||phase!==0;K.$('#p02-options').classList.toggle('hide',demo||phase!==2);
  }
  function reset(){clearTimeout(timer);version++;moved=new Set();phase=0;mistakes=0;demo=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(3,0);render();K.say('先点包住全部七辆的大括号。')}
  K.$('#p02-whole').onclick=function(){if(demo||phase!==0)return;phase=1;K.levels(3,1);K.sfx.ok();K.say('全部七辆。把任务中的三辆移到右边。');render()};
  [2,4,5].forEach(function(n){var b=K.el('button','p02-option',dots(n),K.$('#p02-options'));b.id='p02-answer-'+n;b.setAttribute('aria-label',n+'个数量点');b.onclick=function(){if(phase!==2||demo)return;if(n!==4){mistakes++;K.sfx.no();K.shake(b);K.highlight('#p02-stock');K.say(mistakes===1?'再看看左边，右边的不能算进剩余。':'用手指一辆一辆数左边，再选图。','no');return}phase=3;K.levels(3,3);K.star(1,b);K.sfx.ok();K.say('你找到了留下的部分。','ok');K.$$('.p02-option').forEach(function(x){x.disabled=true});var token=version;timer=setTimeout(function(){if(token!==version)return;K.finish({title:'找到了另一部分',sub:'从整体里去掉发出的部分',again:function(){K.$$('.p02-option').forEach(function(x){x.disabled=false});reset()}})},700)}});
  K.onStart=reset;K.onState=function(s){if(s.resetTask){K.$$('.p02-option').forEach(function(x){x.disabled=false});reset()}if(typeof s.demoMove==='number'){reset();demo=true;phase=1;for(var i=0;i<Math.min(s.demoMove,3);i++)moved.add(i);render();K.say('教师示范：三辆发出，观察留下的部分。')}};
  reset();K.ready({title:'小车出发',sub:'先看全部，再找留下的',emoji:'−'});
})();

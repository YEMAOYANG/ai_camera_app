(function(){
var tasks=[[2,4],[4,2],[3,3]],level=0,a=2,b=4,model=[[],[]],demo=false,busy=false,miss=0,timer;
K.hud({icon:'◉',title:'一只杯子配一枚圆片',levels:3});K.owl();
K.ready({emoji:'◉',title:'一只杯子配一枚圆片',sub:'两边分别摆，每只杯子只配一枚'});
function image(parent,key){
 var urls={cup:'__IMG:cup__',bead:'__IMG:bead__'};
 var unit=K.el('span','unit'+(key==='bead'?' bead':''),'<img src="'+urls[key]+'" alt="">',parent);
 unit.querySelector('img').onerror=function(){this.style.visibility='hidden';this.parentElement.classList.add('fallback')};
}
function clearModel(){model=[Array(a).fill(false),Array(b).fill(false)]}
function render(){
 [a,b].forEach(function(n,side){
  var cups=K.$(side?'#cups-b':'#cups-a'),zone=K.$(side?'#model-right':'#model-left');
  cups.innerHTML='';zone.innerHTML='';
  for(var i=0;i<n;i++){
   image(cups,'cup');
   (function(index){
    var filled=!!model[side][index],slot=K.el('button','model-slot'+(filled?' paired':''),'',zone);
    slot.id='model-slot-'+side+'-'+index;
    slot.setAttribute('aria-label',(side?'右边':'左边')+'第'+(index+1)+'只杯子的圆片位');
    slot.disabled=demo||busy||filled;
    if(filled)image(slot,'bead');
    slot.onclick=function(event){event.stopPropagation();fill(side,index)};
   })(i);
  }
 });K.levels(3,level);
}
function load(){a=tasks[level][0];b=tasks[level][1];clearModel();miss=0;busy=false;render();K.say('一只杯子对应一枚圆片，别多配也别少配。')}
function reset(){clearTimeout(timer);level=0;demo=false;K.stars=0;K.$('#star-n').textContent='0';load()}
function fill(side,index){if(demo||busy||model[side][index])return;model[side][index]=true;render();K.sfx.drop()}
function add(side){
 if(demo||busy)return;
 var index=model[side].indexOf(false);
 if(index<0){K.say('这一边已经逐个配好，再看看另一边。');return}
 fill(side,index);
}
K.drag(K.$('#bead-supply'),{
 enabled:function(){return !demo&&!busy},
 targets:function(){return [K.$('#model-left'),K.$('#model-right')]},
 onDrop:function(el,target){if(target)add(target.id==='model-left'?0:1)},
 onTap:function(){K.highlight('#model-left');K.highlight('#model-right');K.say('再点下面的空位，给对应的杯子配一枚圆片。')}
});
K.$('#bead-supply img').onerror=function(){this.style.visibility='hidden';this.parentElement.classList.add('fallback')};
K.$('#model-left').onclick=function(){add(0)};K.$('#model-right').onclick=function(){add(1)};
K.$('#reset-model').onclick=function(){if(!demo&&!busy){clearModel();render();K.say('模型清空了，可以重新一一配对。')}};
K.$('#check-model').onclick=function(){
 if(demo||busy)return;
 if(model[0].some(function(x){return !x})||model[1].some(function(x){return !x})){
  miss++;K.sfx.no();K.say(miss===1?'上下逐个对应，看看还有漏配的吗？':miss===2?'每只只用一枚圆片，两边要分别对应。':'先配好一边，再看另一边有没有空位。','no');
  if(miss>=3){K.highlight('#cups');miss=0}return;
 }
 busy=true;K.star(1,K.$('#cups'));K.sfx.ok();K.say('两部分都一一对应，模型能帮我们求整体。','ok');
 timer=setTimeout(function(){level++;if(level===tasks.length)K.finish({title:'实物和模型对应好了',sub:'一枚代表一件，再把两部分合起来。',again:reset});else load()},950);
};
K.onStart=reset;
K.onState=function(state){
 clearTimeout(timer);
 if(state.demo){demo=true;a=3;b=3;clearModel();render()}
 if(state.demoModel){demo=true;model=[Array(a).fill(true),Array(b).fill(true)];render()}
 if(state.play)reset();
};load();
})();

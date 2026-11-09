(function(){
var items=[{id:'mouth',src:'__IMG:mouth__'},{id:'fin',src:'__IMG:fin__'},{id:'tail',src:'__IMG:tail__'}],order=[],index=0,tries=0,busy=false,phase='play',selected=false,epoch=0;
var card=K.$('#part-card'),image=K.$('#part-image'),record=K.$('#part-record'),targets=K.$$('.part-target');
var picturesReady=false,pictures=['__IMG:fish-orange__','__IMG:mouth__','__IMG:fin__','__IMG:tail__'];
function loadPictures(){picturesReady=false;var token=epoch,left=pictures.length;pictures.forEach(function(src){var im=new Image();im.onload=function(){if(token===epoch&&--left===0)picturesReady=true};im.onerror=function(){if(token===epoch){picturesReady=false;K.say('图片暂未载入，请点重来或重新打开本页')}};im.src=src})}
K.hud({icon:'◉',title:'装好观察记录',levels:3});K.owl();K.ready({emoji:'◉',title:'装好观察记录',sub:'把照片放到对应位置',btn:'start-btn'});
image.onerror=function(){picturesReady=false;image.style.visibility='hidden';K.say('图片暂时没有载入，请点重来或重新打开本页')};
function show(item){image.style.visibility='visible';image.src=item.src;image.alt='金鱼'+({mouth:'嘴部',fin:'鱼鳍',tail:'尾部'}[item.id])+'近景';card.classList.remove('selected');selected=false;targets.forEach(function(t){t.classList.remove('correct')})}
function reset(){epoch++;phase='play';order=K.shuffle(items);index=0;tries=0;busy=false;record.innerHTML='';K.stars=0;K.$('#star-n').textContent='0';K.levels(3,0);show(order[0]);loadPictures();K.say('看局部照片，再找到它在整鱼上的位置')}
function match(target){if(!K.started||busy||phase!=='play'||!target)return;if(!picturesReady){K.say('图片正在加载，稍等或点重来再试');return}var item=order[index];if(target.dataset.part!==item.id){tries++;K.sfx.no();K.shake(card);if(tries===1)K.say('再看看照片的形状，和整鱼比一比','no');else if(tries===2)K.say(item.id==='mouth'?'沿着鱼头前面找一找':item.id==='tail'?'从头顺着身体往后看':'看看鱼身旁边伸出的部分','no');else{K.highlight('#part-'+item.id);K.say('老师示范位置，再请你放一次','no')}return}
busy=true;target.classList.add('correct');var im=K.el('img','',null,record);im.src=item.src;im.alt='已对应的鱼部位';K.sfx.ok();K.star(1,target);K.say('局部照片与整鱼对应，记录更清楚','ok');var id=epoch;setTimeout(function(){if(id!==epoch)return;index++;if(index===order.length){K.levels(3,3);K.finish({title:'观察卡装好了',sub:'先看局部，再对照整体',again:reset})}else{tries=0;busy=false;show(order[index]);K.levels(3,index)}},800)}
K.drag(card,{enabled:function(){return K.started&&!busy&&phase==='play'},targets:function(){return targets},onTap:function(){selected=true;card.classList.add('selected');K.sfx.pick()},onDrop:function(el,target){match(target)}});
targets.forEach(function(t){t.addEventListener('click',function(){if(selected)match(t)})});K.$('#part-reset').addEventListener('click',reset);
K.onState=function(state){if(state.demo==='mouth'){phase='demo';show(items[0]);K.$('#part-mouth').classList.add('correct');record.innerHTML='';var im=K.el('img','',null,record);im.src=items[0].src;im.alt='老师对应的嘴部照片'}if(state.phase==='play')reset()};K.onStart=reset;reset();
})();

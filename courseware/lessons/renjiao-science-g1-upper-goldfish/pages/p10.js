(function(){
var entries=[{kind:'food',src:'__IMG:feeding__'},{kind:'breath',src:'__IMG:gill__'}],order=[],index=0,tries=0,phase='play',busy=false,selected=false,epoch=0;
var card=K.$('#life-card'),image=K.$('#life-image'),targets=K.$$('.life-lens');
var picturesReady=false,pictures=['__IMG:feeding__','__IMG:mouth__','__IMG:gill__'];
function loadPictures(){picturesReady=false;var token=epoch,left=pictures.length;pictures.forEach(function(src){var im=new Image();im.onload=function(){if(token===epoch&&--left===0)picturesReady=true};im.onerror=function(){if(token===epoch){picturesReady=false;K.say('图片暂未载入，请点重来或重新打开本页')}};im.src=src})}
K.hud({icon:'◉',title:'把线索归入记录',levels:2});K.owl();K.ready({emoji:'◉',title:'把线索归入记录',sub:'看照片，找对应的部位',btn:'start-btn'});
image.onerror=function(){picturesReady=false;image.style.visibility='hidden';K.say('图片未能载入，请点重来或重新打开本页')};
function show(item){image.style.visibility='visible';image.src=item.src;image.alt=item.kind==='food'?'金鱼嘴接近鱼食的取食画面':'金鱼鳃所在位置的近景';selected=false;card.classList.remove('selected')}
function reset(){epoch++;phase='play';index=0;tries=0;busy=false;order=K.shuffle(entries);K.stars=0;K.$('#star-n').textContent='0';targets.forEach(function(t){t.classList.remove('correct');K.$('.life-slot',t).innerHTML=''});K.levels(2,0);show(order[0]);loadPictures();K.say('看清这张照片，再送到对应部位的镜头')}
function match(target){if(!K.started||phase!=='play'||busy||!target)return;if(!picturesReady){K.say('图片正在加载，稍等或点重来再试');return}var item=order[index];if(target.dataset.kind!==item.kind){tries++;K.sfx.no();K.shake(card);if(tries===1)K.say('先看照片给了什么线索，再想想','no');else if(tries===2)K.say('取食要看口，呼吸联系鳃的位置','no');else{K.highlight(item.kind==='food'?'#life-mouth':'#life-gill');K.say('老师指一下对应部位，再由你放入','no')}return}
busy=true;var im=K.el('img','',null,K.$('.life-slot',target));im.src=item.src;im.alt='已归入对应部位的观察照片';target.classList.add('correct');K.sfx.ok();K.star(1,target);K.say('照片和身体部位对应好了','ok');var id=epoch;setTimeout(function(){if(id!==epoch)return;index++;if(index===2){K.levels(2,2);K.finish({title:'线索整理好了',sub:'口取食，鳃呼吸',again:reset})}else{busy=false;tries=0;K.levels(2,index);show(order[index])}},850)}
K.drag(card,{enabled:function(){return K.started&&!busy&&phase==='play'},targets:function(){return targets},onTap:function(){selected=true;card.classList.add('selected');K.sfx.pick()},onDrop:function(el,target){match(target)}});
targets.forEach(function(t){t.addEventListener('click',function(){if(selected)match(t)})});K.$('#life-reset').addEventListener('click',reset);
K.onState=function(state){if(state.demo){phase='demo';var item=entries[state.demo==='food'?0:1];show(item);var target=state.demo==='food'?K.$('#life-mouth'):K.$('#life-gill');targets.forEach(function(t){t.classList.remove('correct');K.$('.life-slot',t).innerHTML=''});target.classList.add('correct');var im=K.el('img','',null,K.$('.life-slot',target));im.src=item.src;im.alt='老师展示的部位线索'}if(state.phase==='play')reset()};K.onStart=reset;reset();
})();

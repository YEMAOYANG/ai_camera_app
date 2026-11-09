function createShapeGame(){
  var answers={ball:'round',book:'long'},placed=new Set(),errors=0;
  return {
    place:function(item,shape){if(!Object.prototype.hasOwnProperty.call(answers,item)||placed.has(item))return {ok:false,duplicate:true};if(answers[item]!==shape){errors++;return {ok:false,hint:errors===1?'再看看外边的样子。':'沿着物品的外边看一圈，再比一比。'};}placed.add(item);return {ok:true};},
    has:function(item){return placed.has(item);},count:function(){return placed.size;},complete:function(){return placed.size===2;},reset:function(){placed.clear();errors=0;}
  };
}
if(typeof module!=='undefined'&&module.exports)module.exports={createShapeGame:createShapeGame};
else(function(){
  var game=createShapeGame(),selected=null,finishTimer=null,items=K.$$('.shape-item');
  K.hud({icon:'',title:'看看外面什么样',levels:2});K.owl();
  function render(){K.levels(2,game.count());items.forEach(function(el){el.classList.toggle('selected',el.dataset.item===selected);el.classList.toggle('placed',game.has(el.dataset.item));});}
  function reset(){clearTimeout(finishTimer);game.reset();selected=null;K.stars=0;K.$('#star-n').textContent='0';items.forEach(function(el){K.$('#shape-tray').appendChild(el);});K.$('#shape-demo-sample').hidden=true;render();K.say('拖动图片，或先点图片再点轮廓。');}
  function place(el,target){
    if(!target){K.say('把图片放到一个轮廓里试一试。');return;}
    if(el.classList.contains('load-error'))return;
    var result=game.place(el.dataset.item,target.dataset.shape);
    if(!result.ok){if(result.hint){K.say(result.hint,'no');K.sfx.no();K.shake(el);}return;}
    target.querySelector('.shape-dock').appendChild(el);selected=null;K.sfx.ok();K.star(1,target);render();K.say('放在一起，外面的样子很相像。','ok');
    if(game.complete())finishTimer=setTimeout(function(){K.finish({title:'两种外形找到了',sub:'圆圆的，长长方方的',again:reset});},650);
  }
  items.forEach(function(el){
    var img=el.querySelector('img'),src=img.src;img.addEventListener('error',function(){el.classList.add('load-error');});img.addEventListener('load',function(){el.classList.remove('load-error');});
    function select(){if(el.classList.contains('load-error')){img.src=src;K.say('正在重新加载图片。');return;}if(!game.has(el.dataset.item)){selected=el.dataset.item;render();K.say('再点一个样子相像的轮廓。');}}
    K.drag(el,{enabled:function(){return !game.has(el.dataset.item)&&!el.classList.contains('load-error');},targets:function(){return K.$$('.shape-target');},onTap:select,onDrop:place});
    el.addEventListener('click',function(e){e.stopPropagation();select();});
  });
  K.$$('.shape-target').forEach(function(target){target.addEventListener('click',function(){if(selected)place(K.$('#shape-'+selected),target);else K.say('先选一张物品图片，再选轮廓。');});target.addEventListener('keydown',function(event){if(event.key==='Enter'||event.key===' '){event.preventDefault();target.click();}});});
  K.onState=function(state){if(state.shapeDemo==='round')K.$('#shape-demo-sample').hidden=false;else if(state.shapeDemo==='reset')K.$('#shape-demo-sample').hidden=true;};
  K.onStart=reset;K.ready({title:'看看外面什么样',sub:'找相像的外形，放在一起',emoji:'',img:'__IMG:campus__'});
})();

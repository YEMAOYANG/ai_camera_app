function createMarkGame(total) {
  var marked = new Set();
  return {
    mark: function (id) { if(!Number.isInteger(id)||id<0||id>=total||marked.has(id))return false;marked.add(id);return true; },
    count: function () { return marked.size; },
    has: function (id) { return marked.has(id); },
    complete: function () { return marked.size===total; },
    reset: function () { marked.clear(); }
  };
}
if(typeof module!=='undefined'&&module.exports)module.exports={createMarkGame:createMarkGame};
else (function(){
  var game=createMarkGame(10),field=K.$('#butterfly-field'),finishTimer=null;
  K.hud({icon:'',title:'数过就做标记',levels:10});K.owl();
  function render(){
    K.$('#mark-count').textContent=game.count();K.levels(10,game.count());
    K.$$('.butterfly-item').forEach(function(button,i){button.classList.toggle('marked',game.has(i));});
  }
  function reset(){clearTimeout(finishTimer);game.reset();K.stars=0;K.$('#star-n').textContent='0';K.$$('.demo-marks>div').forEach(function(el){el.classList.remove('marked');});render();K.say('一只一只数，点过的圈会留下来。');}
  for(var index=0;index<10;index++)(function(id){
    var button=K.el('button','butterfly-item',null,field);button.id='butterfly-item-'+id;
    button.setAttribute('aria-label','标记蝴蝶'+(id+1));button.style.left=(38+(id%5)*168)+'px';button.style.top=(48+Math.floor(id/5)*190)+'px';
    var img=K.el('img','',null,button);img.alt='一只橙黄色蝴蝶';img.src='__IMG:butterfly__';
    img.addEventListener('error',function(){button.classList.add('load-error');});img.addEventListener('load',function(){button.classList.remove('load-error');});
    button.addEventListener('click',function(){
      if(button.classList.contains('load-error')){img.src='__IMG:butterfly__';K.say('正在重新加载图片。');return;}
      if(!game.mark(id)){K.say('这个圈已经有了，再找没有圈的。');K.sfx.no();return;}
      K.sfx.tick(game.count());K.star(1,button);render();K.say('已经标记'+game.count()+'只。','ok');
      if(game.complete())finishTimer=setTimeout(function(){K.finish({title:'十只都数到了',sub:'圈留下来，不重数也不漏数',again:reset});},1200);
    });
  })(index);
  K.onState=function(state){if(Number.isInteger(state.demoMark))K.$$('.demo-marks>div').forEach(function(el,i){el.classList.toggle('marked',i<state.demoMark);});};
  K.onStart=reset;
  K.ready({title:'数过就做标记',sub:'给每只蝴蝶留下一个圈',emoji:'',img:'__IMG:butterfly__'});render();
})();

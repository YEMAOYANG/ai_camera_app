function createBirdGame(total) {
  var counted = new Set();
  return {
    pick: function (id) {
      if (!Number.isInteger(id) || id < 0 || id >= total || counted.has(id)) return false;
      counted.add(id); return true;
    },
    count: function () { return counted.size; },
    has: function (id) { return counted.has(id); },
    complete: function () { return counted.size === total; },
    reset: function () { counted.clear(); }
  };
}
if (typeof module !== 'undefined' && module.exports) module.exports = { createBirdGame: createBirdGame };
else (function () {
  var game = createBirdGame(5), field = K.$('#bird-field'), finishTimer = null;
  K.hud({icon:'',title:'小鸟排队啦',levels:5}); K.owl();
  function render() {
    K.$('#bird-count').textContent = game.count(); K.levels(5,game.count());
    K.$$('.bird-item').forEach(function (button,index) {
      button.classList.toggle('counted',game.has(index));
      button.style.top = game.has(index) ? '76px' : '288px';
    });
  }
  function reset() {
    clearTimeout(finishTimer); game.reset(); K.stars=0; K.$('#star-n').textContent='0';
    K.$$('.demo-birds>div').forEach(function(el){el.classList.remove('marked');});
    render(); K.say('一边点，一边数；每只只点一次。');
  }
  for (var index=0;index<5;index++) (function (id) {
    var button=K.el('button','bird-item',null,field);button.id='bird-item-'+id;
    button.setAttribute('aria-label','点小鸟'+(id+1));button.style.left=(46+id*166)+'px';
    var img=K.el('img','',null,button);img.alt='一只蓝色小鸟';img.src='__IMG:bird__';
    img.addEventListener('error',function(){button.classList.add('load-error');});
    img.addEventListener('load',function(){button.classList.remove('load-error');});
    button.addEventListener('click',function(){
      if(button.classList.contains('load-error')){img.src='__IMG:bird__';K.say('正在重新加载图片。');return;}
      if(!game.pick(id)){K.say('它已经数过了，看看下面的小鸟。');K.sfx.no();return;}
      K.sfx.tick(game.count());K.star(1,button);render();K.say('已经点过'+game.count()+'只。','ok');
      if(game.complete()) finishTimer=setTimeout(function(){K.finish({title:'五只都数到了',sub:'每只只数一次',again:reset});},1200);
    });
  })(index);
  K.onState=function(state){
    if(Number.isInteger(state.demoStep)) K.$$('.demo-birds>div').forEach(function(el,i){el.classList.toggle('marked',i<state.demoStep);});
  };
  K.onStart=reset;
  K.ready({title:'小鸟排队啦',sub:'听老师讲，再点一只数一只',emoji:'',img:'__IMG:campus__'});
  render();
})();

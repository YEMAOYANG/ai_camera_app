(function(){
var tasks=[[6,5],[5,7],[8,3],[4,8],[6,6],[7,4]],lev=0,a=6,b=5,demo=false,busy=false,miss=0,timer;
K.hud({icon:'＋',title:'按总数分一分',levels:tasks.length});K.owl();K.ready({emoji:'＋',title:'把算式送回家',sub:'合一合数量，把卡片拖进托盘'});
function dots(parent,n,blue){var g=K.el('span','part-dots'+(blue?' blue':''),'',parent);for(var i=0;i<n;i++)K.el('i','','',g)}
function card(){K.$('#card-slot').innerHTML='';var e=K.el('div','sum-card','',K.$('#card-slot'));e.id='sum-card';e.setAttribute('data-hit','card');e.setAttribute('aria-label',a+'加'+b+'的数量卡');dots(e,a,false);K.el('em','','＋',e);dots(e,b,true);K.el('b','formula',a+'＋'+b,e);K.drag(e,{enabled:function(el){return !demo&&!busy&&el.parentElement.id==='card-slot'},targets:function(){return [K.$('#bin-11'),K.$('#bin-12')]},onDrop:function(el,target){if(target)place(target.id==='bin-11'?11:12,false)}});K.levels(tasks.length,lev)}
function place(n, forced) {
  if ((demo || busy) && !forced) return;
  var activeCard = K.$('#sum-card');
  if (!activeCard) return;
  if (a + b !== n) {
    miss++;
    K.sfx.no();
    K.say(miss === 1 ? '先把两组点合起来，再想送到哪边。'
      : miss === 2 ? '可以先凑十，再数剩余的点。'
      : '一个十加剩余的几个一，就是总数。', 'no');
    return;
  }
  busy = true;
  activeCard.removeAttribute('data-hit');
  activeCard.style.touchAction = 'auto';
  activeCard.id = forced ? 'demo-card-' + n : 'accepted-card-' + lev;
  K.$('#accepted-' + n).appendChild(activeCard);
  K.$('#bin-' + n).classList.add('good');
  if (forced) return;
  K.star(1, activeCard);
  K.sfx.ok();
  K.say('算式不同，也可能得到相同的总数。', 'ok');
  timer = setTimeout(function () {
    K.$('#bin-' + n).classList.remove('good');
    lev++;
    if (lev === tasks.length) {
      K.finish({title: '数量都分清啦', sub: '先算合起来，再按得数分类。', again: reset});
    } else {
      load();
    }
  }, 900);
}
function load(){a=tasks[lev][0];b=tasks[lev][1];busy=false;miss=0;card();K.say('两组点合起来是十一，还是十二？')}
function clear(){K.$('#accepted-11').innerHTML='';K.$('#accepted-12').innerHTML='';K.$('#bin-11').classList.remove('good');K.$('#bin-12').classList.remove('good')}
function reset(){clearTimeout(timer);demo=false;lev=0;K.stars=0;K.$('#star-n').textContent='0';clear();load()}
K.$('#bin-11').onclick = function () { place(11, false); };
K.$('#bin-12').onclick = function () { place(12, false); };
K.onStart = reset;
K.onState = function (state) {
  if (state.demo) {
    clearTimeout(timer);
    var finish = K.$('#finish');
    if (finish) finish.classList.add('gone');
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    demo = true;
    busy = false;
    lev = 0;
    a = 6;
    b = 5;
    K.say('先看老师示范，再轮到你。');
    clear();
    card();
  }
  if (state.place && demo) place(11, true);
  if (state.exampleTwelve && demo && !K.$('#demo-card-12')) {
    a = 5;
    b = 7;
    card();
  }
  if (state.placeTwelve && demo) place(12, true);
  if (state.play) reset();
};
load();
})();

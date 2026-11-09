(function(){
  'use strict';

  function watchPictures() {
    var pictures=K.$$('img',K.$('#play'));
    var retry=K.el('button','btn sm retry-picture hide','重新打开图片',K.$('#play'));
    function showError(){retry.classList.remove('hide');K.say('图片没有打开，点一下重试。','no');}
    pictures.forEach(function(image){
      image.addEventListener('error',showError);
      if(image.getAttribute('src')&&image.complete&&!image.naturalWidth)showError();
    });
    retry.addEventListener('click',function(){
      retry.classList.add('hide');
      pictures.forEach(function(image){if(image.src&&!image.naturalWidth){var source=image.src;image.removeAttribute('src');image.src=source;}});
    });
  }

  var slots=K.$$('.journal-slot'),cards=K.$$('.journal-choices button'),order=[1,0];
  var step=0,misses=0;
  function show(){slots.forEach(function(slot,i){slot.classList.toggle('selected',i===step);});K.say(step===0?'先放第一次看见的样子。':'再放下一次看见的样子。');}
  function reveal(index){slots[index].querySelector('img').hidden=false;}
  function reset(){
    step=0;misses=0;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);
    slots.forEach(function(slot){slot.querySelector('img').hidden=true;});
    cards.forEach(function(card){card.disabled=false;card.className='choice';});show();
  }
  function choose(index,target){
    if(!K.started||step>=2||!K.$('#journal-reference').naturalWidth)return;
    var card=cards[index];
    if(index!==order[step]||(target&&target!==slots[step])){
      misses++;card.classList.add('miss');K.shake(card);K.sfx.no();
      K.say(misses===1?'先比一比左右两次的样子。':'听清这次要放第几张。','no');
      if(misses>=3)cards[order[step]].classList.add('hint');
      return;
    }
    reveal(step);cards.forEach(function(item){item.classList.remove('miss','hint');});card.disabled=true;card.className='choice good';K.star(1,card);K.sfx.ok();
    step++;misses=0;K.levels(2,step);
    if(step===2){slots.forEach(function(slot){slot.classList.remove('selected');});K.finish({title:'两次画像都留住了',sub:'下一次照实画，再和这次比。',again:reset});return;}
    show();
  }
  cards.forEach(function(card,index){
    K.drag(card,{enabled:function(){return K.started&&step<2&&!card.disabled;},targets:function(){return slots;},
      onTap:function(){choose(index,null);},onDrop:function(el,target){if(target)choose(index,target);}});
    card.addEventListener('click',function(event){if(event.detail===0)choose(index,null);});
  });
  K.hud({icon:'▣',title:'今天一张，下次一张',levels:2});K.owl();K.onStart=reset;
  K.onState=function(state){if(state.practice){reset();return;}if(Number.isInteger(state.time)&&slots[state.time])reveal(state.time);};
  K.ready({emoji:'▣',title:'今天一张，下次一张',sub:'把同一株的两张图分开留好。'});

  watchPictures();
})();

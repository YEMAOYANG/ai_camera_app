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

  var buttons=[K.$('#edit-flower-button'),K.$('#edit-pot-button'),K.$('#edit-leaf-button')];
  var pot=K.$('#edit-pot'),leaf=K.$('#edit-leaf'),flower=K.$('#edit-flower');
  var initialPot=pot.getAttribute('src'),initialLeaf=leaf.getAttribute('src');
  var hints=['先找画上多出来的东西。','再看看画上的容器。','最后对一对叶形。'];
  var step=0,misses=0;
  function correct(index){
    if(index===0)flower.hidden=true;
    else if(index===1)pot.src='__IMG:blue-pot__';
    else if(index===2)leaf.src='__IMG:mint-leaves__';
  }
  function reset(){
    step=0;misses=0;K.stars=0;K.$('#star-n').textContent='0';K.levels(3,0);
    flower.hidden=false;pot.src=initialPot;leaf.src=initialLeaf;
    buttons.forEach(function(button){button.className='choice';button.disabled=false;});K.say(hints[0]);
  }
  function choose(index){
    if(!K.started||step>=3||!K.$('#edit-reference').naturalWidth)return;
    var button=buttons[index];
    if(index!==step){
      misses++;button.classList.add('miss');K.shake(button);K.sfx.no();
      K.say(misses===1?'两边摆在一起，再看这一处。':hints[step],'no');
      if(misses>=3)buttons[step].classList.add('hint');
      return;
    }
    correct(index);buttons.forEach(function(item){item.classList.remove('miss','hint');});button.className='choice good';button.disabled=true;K.star(1,button);K.sfx.ok();
    step++;misses=0;K.levels(3,step);
    if(step===3){K.finish({title:'画像更像实物了',sub:'只留下观察到的样子。',again:reset});return;}
    K.say(hints[step],'ok');
  }
  buttons.forEach(function(button,index){button.addEventListener('click',function(){choose(index);});});
  K.hud({icon:'◇',title:'拿画和实物对一对',levels:3});K.owl();K.onStart=reset;
  K.onState=function(state){if(state.practice){reset();return;}if(Number.isInteger(state.correction)&&buttons[state.correction])correct(state.correction);};
  K.ready({emoji:'◇',title:'拿画和实物对一对',sub:'找出三处不同，逐个改好。'});

  watchPictures();
})();

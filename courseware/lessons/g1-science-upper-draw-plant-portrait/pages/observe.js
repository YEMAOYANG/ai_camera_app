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

  var buttons=K.$$('.marker'), zoom=K.$('#observe-zoom');
  var points=[['36%','57%'],['51%','26%'],['52%','75%']];
  var hints=['找透明的杯壁和水面。','找伸出杯口的细长弯叶。','找杯壁里浅色的细根。'];
  var step=0,misses=0;
  function show(index){
    zoom.style.setProperty('--zoom',index<0?'1':'2.15');
    zoom.style.setProperty('--view-x',index<0?'50%':points[index][0]);
    zoom.style.setProperty('--view-y',index<0?'50%':points[index][1]);
  }
  function reset(){
    step=0;misses=0;K.stars=0;K.$('#star-n').textContent='0';K.levels(3,0);
    buttons.forEach(function(button){button.className='marker';button.disabled=false;});
    show(-1);K.say(hints[0]);
  }
  function choose(index){
    if(!K.started||step>=3||!K.$('#observe-image').naturalWidth)return;
    var button=buttons[index];
    if(index!==step){
      misses++;button.classList.add('miss');K.shake(button);K.sfx.no();
      K.say(misses===1?'先看看整株，再找这处。':hints[step],'no');
      if(misses>=3)buttons[step].classList.add('hint');
      return;
    }
    show(index);buttons.forEach(function(item){item.classList.remove('miss','hint');});button.className='marker good';button.disabled=true;
    K.sfx.ok();K.star(1,button);step++;misses=0;K.levels(3,step);
    if(step===3){K.finish({title:'找齐了三处线索',sub:'杯里的水、弯弯的叶和看得见的根。',again:reset});return;}
    K.say(hints[step],'ok');
  }
  buttons.forEach(function(button,index){button.addEventListener('click',function(){choose(index);});});
  K.hud({icon:'◉',title:'放大镜找线索',levels:3});K.owl();K.onStart=reset;
  K.onState=function(state){if(state.practice){reset();return;}if(Number.isInteger(state.focus)&&points[state.focus]){buttons.forEach(function(button){button.classList.remove('demo');});buttons[state.focus].classList.add('demo');show(state.focus);}};
  K.ready({emoji:'◉',title:'放大镜找线索',sub:'听一听，在图上找三处。'});

  watchPictures();
})();

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

  var cards=K.$$('.choices button'),draft=K.$('#assemble-draft');
  var layers=[K.$('#assemble-pot'),K.$('#assemble-leaf'),K.$('#assemble-detail')];
  var rounds=[
    {images:['__IMG:glass-pot__','__IMG:pothos-pot__','__IMG:blue-pot__'],alts:['水杯','红褐色土盆','蓝陶盆'],answer:1,ask:'先找红褐色花盆。',crop:'translateY(-23%)'},
    {images:['__IMG:pothos-shape__','__IMG:spider-leaves__','__IMG:mint-wrong-leaves__'],alts:['宽宽的心形叶','细长弯叶','圆叶'],answer:0,ask:'再找宽宽的、尖头的叶。',crop:'translateY(23%)'},
    {images:['__IMG:red-flower__','__IMG:hidden-roots__','__IMG:pothos-vein__'],alts:['额外的红花','没看见的根','叶面线条'],answer:2,ask:'最后找叶面上看得见的线。',crop:'translateY(18%)'}
  ];
  var step=0,misses=0;
  function show(){
    var round=rounds[step];misses=0;
    cards.forEach(function(card,i){
      var picture=card.querySelector('img');picture.src=round.images[i];picture.alt=round.alts[i];
      picture.style.transform=round.crop;card.setAttribute('aria-label',round.alts[i]);card.className='choice';
    });
    K.say(round.ask);
  }
  function reset(){
    step=0;K.stars=0;K.$('#star-n').textContent='0';K.levels(3,0);
    layers.forEach(function(layer){layer.hidden=true;});draft.classList.remove('ready');show();
  }
  function choose(index){
    if(!K.started||step>=3||!K.$('#assemble-reference').naturalWidth)return;
    var current=rounds[step],card=cards[index];
    if(index!==current.answer){
      misses++;card.classList.add('miss');K.shake(card);K.sfx.no();
      K.say(misses===1?'再和左边的实物比一比。':current.ask,'no');
      if(misses>=3)cards[current.answer].classList.add('hint');
      return;
    }
    layers[step].hidden=false;draft.classList.add('ready');K.sfx.ok();K.star(1,card);
    step++;K.levels(3,step);
    if(step===3){K.finish({title:'画像拼好了',sub:'实物里看得见的特征，画纸上找得到。',again:reset});return;}
    show();
  }
  cards.forEach(function(card,index){
    K.drag(card,{enabled:function(){return K.started&&step<3;},targets:function(){return [draft];},
      onTap:function(){choose(index);},onDrop:function(el,target){if(target)choose(index);}});
    card.addEventListener('click',function(event){if(event.detail===0)choose(index);});
  });
  K.hud({icon:'✎',title:'给眼前这株画像',levels:3});K.owl();K.onStart=reset;
  K.onState=function(state){
    if(state.practice){reset();return;}
    if(Number.isInteger(state.layer)&&layers[state.layer]){
      layers.forEach(function(layer,index){layer.hidden=index>state.layer;});
      draft.classList.add('ready');
    }
  };
  K.ready({emoji:'✎',title:'给眼前这株画像',sub:'选一张图卡，放进画纸。'});

  watchPictures();
})();

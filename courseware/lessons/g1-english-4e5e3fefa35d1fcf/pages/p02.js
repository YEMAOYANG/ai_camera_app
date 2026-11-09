(function(){
  'use strict';
  const cfg=JSON.parse(document.getElementById('lesson-data').textContent);
  const frame=document.getElementById('photo-target');
  const result=document.getElementById('result-photo');
  const prompt=document.getElementById('target-word');
  const track=document.getElementById('photo-track');
  const speaker=document.getElementById('prompt-audio');
  const cards=Array.from(document.querySelectorAll('.photo-card'));
  let round=0,misses=0,locked=false,handoff=false,pending=null,clip=null,epoch=0;
  K.hud({icon:'',title:cfg.title,levels:cfg.trials.length});K.owl();
  K.ready({emoji:'',title:cfg.title,sub:'',btn:'start-btn'});
  function pause(){if(clip){clip.pause();clip.currentTime=0;clip=null}}
  function speak(){
    pause();const url=cfg.trials[round].audio;
    if(!handoff||!url||url.indexOf('__VOICE:')===0)return;
    clip=new Audio(url);clip.preload='auto';
    clip.addEventListener('error',function(){speaker.classList.add('audio-failed')},{once:true});
    clip.play().then(function(){speaker.classList.remove('audio-failed')}).catch(function(){speaker.classList.add('audio-failed')});
  }
  function showPhoto(key){
    const card=document.getElementById('card-'+key);
    result.src=card.querySelector('img').src;result.alt=card.querySelector('img').alt;
    result.hidden=false;frame.classList.add('occupied');
  }
  function clearPhoto(){result.hidden=true;result.removeAttribute('src');frame.classList.remove('occupied')}
  function render(){
    const t=cfg.trials[round];misses=0;locked=false;clearPhoto();
    prompt.textContent=handoff?t.word:'';frame.dataset.job=handoff?(t.place||''):'';
    cards.forEach(function(card){
      card.hidden=t.choices.indexOf(card.dataset.key)<0;
      card.disabled=false;card.classList.remove('placed','answer-hint');
    });
    K.levels(cfg.trials.length,round);
    K.say('\u5148\u542c\u5f55\u97f3\uff0c\u518d\u628a\u7167\u7247\u9001\u8fdb\u4e2d\u95f4');
  }
  function reset(){
    epoch++;if(pending)clearTimeout(pending);pending=null;pause();
    round=0;track.replaceChildren();K.stars=0;
    document.getElementById('star-n').textContent='0';
    const finish=document.getElementById('finish');if(finish)finish.classList.add('gone');
    render();
  }
  function choose(key){
    if(!K.started||!handoff||locked)return;
    const t=cfg.trials[round],card=document.getElementById('card-'+key);
    if(card.hidden)return;
    if(card.classList.contains('image-failed')){const im=card.querySelector('img');card.classList.remove('image-failed');im.src=im.getAttribute('src');return}
    if(key!==t.key){
      misses++;K.sfx.no();K.shake(card);
      K.say(misses===1?'\u518d\u542c\u4e00\u6b21\uff0c\u60f3\u60f3\u8bf4\u7684\u662f\u8c01':misses===2?'\u770b\u6e05\u4eba\u7269\u548c\u5de5\u4f5c\u7ebf\u7d22':'\u8ddf\u7740\u793a\u8303\uff0c\u518d\u9001\u8fd9\u5f20\u7167\u7247','no');
      if(misses>=3)document.getElementById('card-'+t.key).classList.add('answer-hint');
      speak();
      return;
    }
    locked=true;pause();card.classList.add('placed');showPhoto(key);K.sfx.ok();K.star(1,card);
    const thumb=card.querySelector('img').cloneNode(true);thumb.removeAttribute('id');track.appendChild(thumb);
    K.say('\u7167\u7247\u548c\u4ecb\u7ecd\u8fde\u4e0a\u4e86','ok');
    const e=epoch;
    pending=setTimeout(function(){
      if(e!==epoch)return;
      if(round===cfg.trials.length-1){K.levels(cfg.trials.length,cfg.trials.length);K.finish({title:'\u7167\u7247\u90fd\u9001\u5230\u4e86',sub:'\u542c\u9009\u5df2\u8bb0\u5f55\uff0c\u5f00\u53e3\u8868\u8fbe\u5f85\u89c2\u5bdf',again:function(){reset();handoff=true}})}
      else{round++;render();speak()}
    },900);
  }
  cards.forEach(function(card){
    K.drag(card,{enabled:function(){return K.started&&handoff&&!locked&&!card.hidden},targets:function(){return[frame]},
      onTap:function(){choose(card.dataset.key)},onDrop:function(el,target){if(target===frame)choose(el.dataset.key);else K.sfx.drop()}});
    card.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(card.dataset.key)}});
    card.querySelector('img').addEventListener('error',function(){card.classList.add('image-failed')});
  });
  speaker.addEventListener('click',speak);
  document.getElementById('start-btn').addEventListener('click',function(){handoff=true;render();speak()});
  K.onState=function(state){
    if(Object.prototype.hasOwnProperty.call(state,'demo')){
      pause();if(state.demo){
        locked=true;
        const trial=cfg.trials.find(function(t){return t.key===state.demo});
        prompt.textContent=trial?trial.word:(cfg.demoWord||'');
        frame.dataset.job=trial&&trial.place||'';
        showPhoto(state.demo);
      }else{reset()}
    }
    if(state.handoff===true){handoff=true;render();speak()}
    if(state.handoff===false){handoff=false;pause()}
  };
  window.addEventListener('pagehide',pause);
  window.addEventListener('message',function(e){
    const message=e.data||{};
    if(message.type==='PAUSE_WIDGET_AUDIO')pause();
    if(!handoff&&locked&&message.type==='HIGHLIGHT_ELEMENT'&&message.target===cfg.clearDemoAt){
      clearPhoto();prompt.textContent='';frame.dataset.job='';
    }
  });
  window.__test=async function(){
    const checks=[];const ok=function(n,v){K.check(checks,n,v)};
    K.sim.click(document.getElementById('start-btn'));pause();
    const wrong=cfg.trials[0].choices.find(function(k){return k!==cfg.trials[0].key});
    K.sim.tap(document.getElementById('card-'+wrong));
    ok('first wrong does not reveal',!document.querySelector('.answer-hint')&&result.hidden);
    await K.cp('first-wrong');
    K.onState({demo:cfg.trials[0].key});
    ok('teacher demonstrates real photo',!result.hidden&&frame.classList.contains('occupied'));
    await K.cp('teacher-demo');
    K.onState({demo:null,handoff:true});pause();
    for(let i=0;i<cfg.trials.length;i++){
      K.sim.tap(document.getElementById('card-'+cfg.trials[i].key));
      ok('photo moves '+i,!result.hidden&&document.getElementById('card-'+cfg.trials[i].key).classList.contains('placed'));
      if(i===0)await K.cp('correct');
      await K.wait(1050);pause();
    }
    ok('finish visible',!document.getElementById('finish').classList.contains('gone'));
    await K.cp('finish');K.sim.click(document.getElementById('btn-again'));
    ok('again fully resets',round===0&&track.children.length===0&&result.hidden&&K.stars===0&&!locked);
    await K.cp('reset');return checks;
  };
  render();
})();

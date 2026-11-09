(function(){
  var rules={fresh:function(){return {done:false,misses:0}},choose:function(s,key){if(s.done)return s;return key==='walk'?{done:true,misses:s.misses}:{done:false,misses:s.misses+1}}};
  window.BellRules=rules;if(window.__RULES_ONLY__)return;
  var mediaBlocked=false;function mediaFailure(){mediaBlocked=true;K.$('#lesson-media-error').classList.remove('hide')}
  K.$$('#play img').forEach(function(im){im.addEventListener('error',mediaFailure);if(im.getAttribute('src')&&im.complete&&im.naturalWidth===0)mediaFailure()});
  K.$('#lesson-media-retry').addEventListener('click',function(){window.location.reload()});

  var s=rules.fresh(),demo=false,token=0,walk=K.$('#bell-walk'),play=K.$('#bell-play'),view=K.$('#bell-view');
  var images={play:'__IMG:keep-play__',walk:'__IMG:walk-class__',ready:'__IMG:class-ready__'};
  function reset(){token++;s=rules.fresh();demo=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(1,0);walk.disabled=play.disabled=false;walk.classList.remove('chosen');view.src=images.play;view.alt='孩子还在操场';K.$('#bell-demo').classList.add('hide');K.say('听一听上课信号，再选一个行动。');}
  function choose(key){if(mediaBlocked||demo||s.done)return;var before=s;s=rules.choose(s,key);if(s===before)return;if(!s.done){K.shake(play);K.sfx.no();K.say(s.misses===1?'想一想，这个信号在提醒什么？':s.misses===2?'这是开始上课的信号。':'现在需要回教室，安静坐好。','no');return;}
    walk.disabled=play.disabled=true;walk.classList.add('chosen');view.src=images.ready;view.alt='孩子们回到教室安静坐好';K.levels(1,1);K.star(1,walk);K.sfx.ok();K.say('选出了上课前的行动。','ok');var t=token;
    var loaded=typeof view.decode==='function'?view.decode():Promise.resolve();
    loaded.then(function(){if(t!==token||demo)return;setTimeout(function(){if(t===token&&!demo)K.finish({title:'回教室，准备好',sub:'跟着本校的上课信号行动',again:reset})},900);}).catch(function(){if(t===token&&!demo)mediaFailure()});}
  walk.addEventListener('click',function(){choose('walk')});play.addEventListener('click',function(){choose('play')});
  K.onState=function(v){if(v.mode==='demo'){token++;demo=true;view.src=images.ready;view.alt='老师示范：回教室坐好';K.$('#bell-demo').classList.remove('hide');walk.disabled=play.disabled=true;K.say('老师示范：按信号回教室，安静坐好。');}else if(v.mode==='practice')reset()};
  K.hud({icon:'',title:'铃声里的约定',levels:1});K.owl();reset();
  K.ready({title:'铃声里的约定',sub:'听老师讲，再选行动',emoji:'图片暂未载入',onStart:function(){K.sfx.tick()}});
})();

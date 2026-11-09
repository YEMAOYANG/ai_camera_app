(function(){
 var order=['book','note','case'];
 var rules={fresh:function(){return {placed:[],misses:0}},drop:function(s,item,target){if(s.placed.length===3)return s;var next=order[s.placed.length],dest=next==='case'?'case':'stack';return item===next&&target===dest?{placed:s.placed.concat(item),misses:0}:{placed:s.placed.slice(),misses:s.misses+1}}};
 window.DeskRules=rules;if(window.__RULES_ONLY__)return;
  var mediaBlocked=false;function mediaFailure(){mediaBlocked=true;K.$('#lesson-media-error').classList.remove('hide')}
  K.$$('#play img').forEach(function(im){im.addEventListener('error',mediaFailure);if(im.getAttribute('src')&&im.complete&&im.naturalWidth===0)mediaFailure()});
  K.$('#lesson-media-retry').addEventListener('click',function(){window.location.reload()});

 var s=rules.fresh(),selected=null,demo=false,token=0,buttons=K.$$('.supply'),stack=K.$('#desk-stack'),box=K.$('#desk-case');
 var shown={book:K.$('#desk-book-shown'),note:K.$('#desk-note-shown'),case:K.$('#desk-case-shown')};
 function paint(){buttons.forEach(function(b){var placed=s.placed.indexOf(b.dataset.item)>=0;b.classList.toggle('stored',placed);b.classList.toggle('selected',b.dataset.item===selected);b.disabled=placed||demo});Object.keys(shown).forEach(function(key){shown[key].classList.toggle('hide',!demo&&s.placed.indexOf(key)<0)});K.$('span',stack).classList.toggle('hide',demo||s.placed.length>0);K.$('span',box).classList.toggle('hide',demo||s.placed.length===3);stack.classList.toggle('active',!demo&&s.placed.length<2);box.classList.toggle('active',!demo&&s.placed.length===2);K.levels(3,s.placed.length);}
 function reset(){token++;s=rules.fresh();demo=false;selected=null;K.stars=0;K.$('#star-n').textContent='0';K.$('#desk-demo').classList.add('hide');paint();K.say('先摆数学书，再摆练习本，最后摆文具盒。');}
 function drop(item,target){if(mediaBlocked||demo||s.placed.indexOf(item)>=0)return;var n=s.placed.length;s=rules.drop(s,item,target);if(s.placed.length===n){K.sfx.no();K.say(s.misses===1?'再看一看要摆的用品和位置。':s.misses===2?'先摆书和本，再摆文具盒。':'书本放左上角，文具盒放正前方。','no');return;}
 selected=null;paint();K.star(1,shown[item]);K.sfx.ok();K.say(s.placed.length===1?'数学书摆好了，再把练习本叠上去。':s.placed.length===2?'书本叠整齐了，再摆文具盒。':'三类用品齐全，桌面也留出了空间。','ok');if(s.placed.length===3){var t=token;setTimeout(function(){if(t===token&&!demo)K.finish({title:'学具摆整齐了',sub:'向家人说一说每样用品在哪里',again:reset})},900);}}
 buttons.forEach(function(b){b.addEventListener('click',function(){if(b.disabled||demo)return;selected=b.dataset.item;paint();K.sfx.pick()});K.drag(b,{enabled:function(){return !b.disabled&&!demo},targets:function(){return [stack,box]},onTap:function(){selected=b.dataset.item;paint()},onDrop:function(el,target){drop(el.dataset.item,target===stack?'stack':target===box?'case':'outside')}})});
 stack.addEventListener('click',function(){if(selected)drop(selected,'stack')});box.addEventListener('click',function(){if(selected)drop(selected,'case')});
 K.onState=function(v){if(v.mode==='demo'){token++;demo=true;selected=null;K.$('#desk-demo').classList.remove('hide');paint();K.say('老师示范：书本叠好，文具盒放在正前方。');}else if(v.mode==='practice')reset()};
 K.hud({icon:'',title:'学具各就各位',levels:3});K.owl();reset();K.ready({title:'学具各就各位',sub:'可以拖动，也可以先点用品再点位置',emoji:'图片暂未载入',onStart:function(){}});
})();

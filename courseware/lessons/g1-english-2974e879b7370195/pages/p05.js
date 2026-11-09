(function(){
  function makeCounter(total){return {total:total,seen:new Set(),touch:function(id){if(!Number.isInteger(id)||id<1||id>this.total||this.seen.has(id))return false;this.seen.add(id);return true;},count:function(){return this.seen.size;},done:function(){return this.seen.size===this.total;},reset:function(){this.seen.clear();}};}
  if(typeof module==='object'&&module.exports)module.exports={makeCounter:makeCounter};
  if(typeof document==='undefined')return;
  var model=makeCounter(12),demo=false,timer;
  K.hud({icon:'',title:'每只只数一次',levels:1});K.owl();
  function update(){var n=model.count();K.$('#count-number').textContent=n;K.$('#count-word').textContent=n===11?'eleven':n===12?'twelve':'';}
  function touch(id){if(demo||model.done())return;var b=K.$('#count-cat-'+id);if(!model.touch(id)){K.sfx.no();K.shake(b);K.say('这只已经到地垫了，不重复数。','no');return;}b.classList.add('counted');K.$('#counted-strip').appendChild(b);K.sfx.pick();update();if(model.done()){K.star(1,b);K.sfx.ok();K.levels(1,1);K.say('每只只数一次，一共十二只。','ok');timer=setTimeout(function(){K.finish({title:'全部数清了',sub:'11 eleven · 12 twelve',again:reset});},1200);}else K.say('数过的小猫到地垫，接着数剩下的。');}
  function render(count){model.reset();K.$('#count-cat-grid').innerHTML='';K.$('#counted-strip').innerHTML='';for(var i=1;i<=12;i++){var button=K.el('button','count-cat',null,K.$('#count-cat-grid'));button.id='count-cat-'+i;button.setAttribute('aria-label','第'+i+'只小猫');var img=K.el('img','',null,button);img.src='__IMG:cat-orange__';img.alt='一只橙色小猫';img.addEventListener('error',function(){K.$('#image-recovery').classList.remove('hide');});(function(id,b){b.addEventListener('click',function(){touch(id);});})(i,button);if(i<=count){model.touch(i);button.classList.add('counted');K.$('#counted-strip').appendChild(button);}}update();}
  function reset(){clearTimeout(timer);demo=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(1,0);render(0);K.say('点一只，数一次；数过的到地垫。');}
  K.onState=function(state){if('demoCount'in state){clearTimeout(timer);demo=state.demoCount>0;render(Math.max(0,Math.min(12,state.demoCount)));}};
  K.$('#retry-pictures').addEventListener('click',function(){K.$('#image-recovery').classList.add('hide');K.$$('#play img').forEach(function(img){img.src=img.src;});});
  reset();K.onStart=reset;K.ready({title:'每只小猫只数一次',sub:'点一只，数一次',emoji:''});
})();

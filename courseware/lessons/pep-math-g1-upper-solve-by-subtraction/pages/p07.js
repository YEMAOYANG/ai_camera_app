(function(){
  var chosen=0,demo=false,done=false,mistakes=0,timer=null,version=0,total=7,shipped=3;
  K.hud({title:'两部分合回检查',icon:'+',levels:2});K.owl();
  function unit(extra){var d=K.el('span','p07-unit'+(extra?' selected':''),'<img src="__IMG:toy-car__" alt="一辆小车"><i data-semantic-diagram="图片失败时一辆车对应一个数量点"></i>');K.$('img',d).addEventListener('error',function(){this.parentElement.classList.add('failed')});return d}
  function fill(el,n,extra){el.innerHTML='';for(var i=0;i<n;i++)el.appendChild(unit(extra))}
  fill(K.$('#p07-original-cars'),7,false);fill(K.$('#p07-shipped-cars'),3,false);
  function render(){fill(K.$('#p07-original-cars'),total,false);fill(K.$('#p07-shipped-cars'),shipped,false);K.$('#p07-total').textContent=total+' 辆';var box=K.$('#p07-combined-cars');fill(box,shipped,false);for(var i=0;i<chosen;i++)box.appendChild(unit(true));K.$$('.p07-choice').forEach(function(b){b.classList.toggle('chosen',Number(b.dataset.count)===chosen);b.disabled=demo||done});K.$('#p07-check').disabled=!chosen||demo||done}
  function reset(){clearTimeout(timer);version++;chosen=0;demo=false;done=false;mistakes=0;total=7;shipped=3;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);render();K.say('选一张留下的图卡，再按对勾合回检查。')}
  [3,4,5].forEach(function(n){var b=K.el('button','p07-choice','',K.$('#p07-choices'));b.id='p07-choice-'+n;b.dataset.count=String(n);b.setAttribute('aria-label','留下'+n+'辆小车');for(var i=0;i<n;i++)b.appendChild(unit(false));b.onclick=function(){if(demo||done)return;chosen=n;K.sfx.pick();K.levels(2,1);render();K.say('把合回的小车和上面原来的数量比一比。')}});
  K.$('#p07-check').onclick=function(){if(!chosen||demo||done)return;if(chosen+shipped!==total){mistakes++;K.sfx.no();K.shake(K.$('#p07-combined'));K.say(mistakes===1?'合回后和原来一样多吗？再比较。':'上面原来七辆，逐辆对着数一遍。','no');K.highlight('#p07-original');return}done=true;K.star(1,K.$('#p07-check'));K.levels(2,2);render();K.sfx.ok();K.say('发出的和留下的合回，正好是原来的七辆。','ok');var token=version;timer=setTimeout(function(){if(token!==version)return;K.finish({title:'检查对上了',sub:'去掉的部分与留下的部分能合回整体',again:reset})},700)};
  K.onStart=reset;K.onState=function(s){if(s.resetTask)reset();if(typeof s.demoChoose==='number'){reset();total=5;shipped=2;chosen=s.demoChoose;demo=true;render();K.say('教师示范：把发出的和留下的合回看。')}};
  reset();K.ready({title:'合回去查一查',sub:'把两部分合起来，对照原来全部',emoji:'+'});
})();

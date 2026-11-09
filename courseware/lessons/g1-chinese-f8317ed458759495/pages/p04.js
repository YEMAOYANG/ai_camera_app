(() => {
  const card=K.$('#weather-token'), tiles=K.$$('.weather-tile');
  const rounds=[['风','wind'],['雨','rain']];
  let level=0, misses=0, selected=false, demo=false, busy=false, timer;
  const pick=()=>{if(!busy&&!demo){selected=!selected;card.setAttribute('aria-pressed',String(selected));K.sfx.pick()}};
  function resetTiles(){
    for(const tile of tiles){
      delete tile.dataset.ok;delete tile.dataset.miss;
      tile.querySelector('.weather-stamp').textContent='';
    }
  }
  function render(){
    clearTimeout(timer);resetTiles();busy=false;selected=false;misses=0;
    card.setAttribute('aria-pressed','false');card.hidden=false;
    card.textContent=demo?'雨':rounds[level][0];
    K.levels(rounds.length,level);
    K.say(demo?'':'点字卡，再点图。也可以拖过去。');
  }
  function result(tile){
    if(tile.classList.contains('image-broken')){reload(tile);return}
    if(busy||demo)return;
    if(!selected){K.say('先点上方字卡，或把字卡拖过来。');return}
    if(tile.dataset.kind!==rounds[level][1]){
      misses++;tile.dataset.miss='true';K.shake(tile);K.sfx.no();
      const guide=rounds[level][1]==='rain'?'找往下落的小水滴。':'看哪张图里的东西在飘。';
      K.say(misses===1?'这次没配上。想一想字卡说的是哪种天气。':guide,'no');
      if(misses>=3)K.highlight('.weather-tile[data-kind="'+rounds[level][1]+'"]');
      return;
    }
    busy=true;resetTiles();tile.dataset.ok='true';tile.querySelector('.weather-stamp').textContent=rounds[level][0];
    card.hidden=true;K.levels(rounds.length,level+1);K.star(1,tile);K.sfx.ok();K.say('配上了！','ok');
    timer=setTimeout(()=>{
      level++;
      if(level<rounds.length){render();return}
      K.finish({title:'天气配好了',sub:'风和雨，都找到自己的图。',again:reset});
    },850);
  }
  function reset(){demo=false;level=0;K.stars=0;K.$('#star-n').textContent='0';render()}
  function reload(tile){
    const img=tile.querySelector('img');
    tile.classList.remove('image-broken');
    img.src=img.dataset.original;
  }
  for(const tile of tiles){
    const img=tile.querySelector('img');img.dataset.original=img.getAttribute('src');
    img.addEventListener('error',()=>{tile.classList.add('image-broken');K.say('图没打开。点这张图再试。','no')});
    tile.addEventListener('click',()=>result(tile));
  }
  K.drag(card,{enabled:()=>!busy&&!demo,targets:()=>tiles,onTap:pick,onDrop:(_el,tile)=>{if(tile){selected=true;result(tile)}}});
  card.addEventListener('click',event=>{if(event.detail===0)pick()});
  K.hud({icon:'◇',title:'天气字卡',levels:2});K.owl();
  K.onStart=reset;
  K.onState=state=>{
    if(!Object.hasOwn(state,'weatherDemo'))return;
    demo=Boolean(state.weatherDemo);level=0;render();
    if(state.weatherDemo===true){tiles[0].dataset.ok='true';tiles[0].querySelector('.weather-stamp').textContent='雨'}
  };
  K.ready({emoji:'◇',title:'字卡送到天气里',sub:'看天气，给字卡找地方。'});
})();

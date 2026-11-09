(() => {
  const images={flower:['__IMG:flower__','花'],tree:['__IMG:tree__','树'],bird:['__IMG:bird__','鸟'],insect:['__IMG:insect__','虫']};
  const source=K.$('#pair-left'), upper=K.$('#pair-option-tree'), lower=K.$('#pair-option-other');
  const path=K.$('#pair-connection');
  const rounds=[['bird','tree','insect',1],['insect','bird','flower',0]];
  let active=false, demo=false, busy=false, level=0, misses=0, timer;
  const cards=[source,upper,lower];
  function show(card,key){
    const img=card.querySelector('img'), [url,alt]=images[key];
    card.dataset.url=url;card.setAttribute('aria-label',alt);img.alt=alt;
    card.classList.remove('image-broken');
    img.src=url;
  }
  function render(example=false){
    clearTimeout(timer);active=false;busy=false;misses=0;path.setAttribute('d','');
    const [left,a,b]=example?['flower','tree','insect']:rounds[level];
    for(const [card,key] of [[source,left],[upper,a],[lower,b]]){
      delete card.dataset.picked;delete card.dataset.miss;show(card,key);
    }
    K.levels(2,level);
    K.say(example?'看两边怎样配在一起。':'点左图，再点右边的伙伴。');
  }
  function lineTo(index){
    path.setAttribute('d',index?'M 395 275 Q 590 275 807 405':'M 395 275 Q 590 275 807 143');
  }
  function setExample(){
    demo=true;level=0;render(true);active=false;source.dataset.picked='true';upper.dataset.picked='true';lineTo(0);
  }
  function retryImage(card){
    if(!card.classList.contains('image-broken'))return false;
    card.classList.remove('image-broken');card.querySelector('img').src=card.dataset.url;return true;
  }
  source.onclick=()=>{
    if(retryImage(source)||busy||demo)return;
    active=true;source.dataset.picked='true';K.sfx.pick();K.say('再点右边一个伙伴。');
  };
  function choose(index){
    const card=index?lower:upper;
    if(retryImage(card)||busy||demo)return;
    if(!active){K.say('先点左图，再点右边。');return}
    if(index!==rounds[level][3]){
      misses++;card.dataset.miss='true';K.shake(card);K.sfx.no();
      K.say(misses===1?'这两样不太配，再看一看。':'左边是动物，右边也找动物。','no');
      if(misses>=3)K.highlight(rounds[level][3]?'#pair-option-other':'#pair-option-tree');
      return;
    }
    busy=true;delete upper.dataset.miss;delete lower.dataset.miss;card.dataset.picked='true';lineTo(index);
    K.sfx.ok();K.star(1,card);K.levels(2,level+1);K.say('这两样有关，配在一起了。','ok');
    timer=setTimeout(()=>{
      level++;
      if(level<rounds.length){render();return}
      K.finish({title:'对子连起来了',sub:'两边意思有关。',again:reset});
    },900);
  }
  upper.onclick=()=>choose(0);lower.onclick=()=>choose(1);
  for(const card of cards)card.querySelector('img').addEventListener('error',()=>{card.classList.add('image-broken');K.say('图没打开，点一下再试。','no')});
  function reset(){demo=false;level=0;K.stars=0;K.$('#star-n').textContent='0';render()}
  K.hud({icon:'◇',title:'对子牵线',levels:2});K.owl();K.onStart=reset;
  K.onState=state=>{
    if(!Object.hasOwn(state,'pairDemo'))return;
    if(state.pairDemo==='prepare'){demo=true;level=0;render(true)}
    else if(state.pairDemo===true)setExample();else reset();
  };
  K.ready({emoji:'◇',title:'给对子牵线',sub:'给左边找一个伙伴。'});
})();

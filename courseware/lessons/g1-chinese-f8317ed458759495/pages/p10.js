(() => {
  const view=K.$('#spring-view'),img=K.$('#spring-image'),retry=K.$('#spring-retry');
  const word=K.$('#spring-word'),zoom=K.$('#spring-close'),buttons=K.$$('.spring-hit');
  const rounds=['water','willow','peach'];
  const scenes={mountain:['山清','42% 13%'],water:['水秀','55% 82%'],willow:['柳绿','12% 45%'],peach:['桃红','88% 36%']};
  const clues={water:'找有水纹、会映出亮光的地方。',willow:'找往下垂的绿枝叶。',peach:'找树上粉红色的花。'};
  let level=0,misses=0,demo=false,busy=false,timer;
  function clearMarks(){for(const b of buttons)delete b.dataset.state;delete zoom.dataset.show}
  function reset(){
    clearTimeout(timer);demo=false;level=0;busy=false;K.stars=0;K.$('#star-n').textContent='0';render();
  }
  function render(){
    clearMarks();busy=false;misses=0;word.textContent=scenes[rounds[level]][0];
    K.levels(3,level);K.say('在图中找一找，点一个镜头。');
  }
  function focus(key){
    clearMarks();const hit=buttons.find(b=>b.dataset.key===key);
    hit.dataset.state='ok';zoom.style.backgroundPosition=scenes[key][1];zoom.dataset.show='true';
    word.textContent=scenes[key][0];return hit;
  }
  function locate(b){
    if(busy||demo||!retry.hidden)return;
    const key=rounds[level];
    if(b.dataset.key!==key){
      misses++;b.dataset.state='no';K.shake(b);K.sfx.no();
      K.say(misses===1?'这个镜头没找到。再看形状和颜色。':clues[key],'no');
      if(misses>=3)K.highlight('#spring-'+key);
      return;
    }
    busy=true;const hit=focus(key);K.sfx.ok();K.star(1,hit);K.levels(3,level+1);K.say('镜头找对了！','ok');
    timer=setTimeout(()=>{
      level++;
      if(level<rounds.length){render();return}
      K.finish({title:'收好春景',sub:'把山水和春色带进歌里。',again:reset});
    },1150);
  }
  for(const b of buttons)b.onclick=()=>locate(b);
  const url=img.getAttribute('src');
  img.addEventListener('error',()=>{for(const b of buttons)b.disabled=true;retry.hidden=false;K.say('风景图没打开，点一下再试。','no')});
  img.addEventListener('load',()=>{retry.hidden=true;for(const b of buttons)b.disabled=false});
  retry.onclick=()=>{img.src=url};
  K.hud({icon:'◇',title:'春景镜头',levels:3});K.owl();K.onStart=reset;
  K.onState=state=>{
    if(!Object.hasOwn(state,'springDemo'))return;
    if(state.springDemo){demo=true;focus('mountain');K.say('山清。')}
    else reset();
  };
  K.ready({emoji:'◇',title:'用小镜头找春景',sub:'看看歌里的风景。'});
})();

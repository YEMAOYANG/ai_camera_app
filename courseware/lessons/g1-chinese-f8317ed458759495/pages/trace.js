(() => {
  const glyphs={
    cloud:['云',['M34 26 Q48 24 63 24','M22 45 Q50 43 75 43','M49 46 Q43 61 32 72 L63 67','M61 62 Q71 66 77 80']],
    rain:['雨',['M26 21 Q49 21 75 21','M25 36 L25 79','M25 37 H77 V74 Q77 84 70 82 L67 78','M51 23 L51 80','M34 46 L42 51','M34 61 L42 66','M59 45 L67 50','M59 61 L67 66']],
    insect:['虫',['M29 33 L33 57','M31 34 L70 31 L65 55','M34 55 L66 53','M51 18 L51 73','M23 77 Q44 75 67 68','M63 64 Q74 70 78 81']],
    mountain:['山',['M50 18 L50 74','M26 41 L26 75 L75 73','M75 38 L74 82']],
    water:['水',['M51 18 L52 78 Q52 85 47 82 L42 77','M21 44 L40 40 Q35 61 18 76','M74 34 L58 51','M57 49 Q69 69 86 77']]
  };
  const rounds=document.title==='再描山和水'?['mountain','water']:['cloud','rain','insect'];
  const grid=K.$('#ink-grid'),paths=K.$('#ink-paths'),word=K.$('#ink-word');
  const show=K.$('#ink-show'),redo=K.$('#ink-redo');
  const aside=K.$('#ink-example'), picture=K.$('#ink-image');
  const pictures={rain:['__IMG:rain__','雨滴与水洼'],insect:['__IMG:insect__','叶上的小虫'],
    mountain:['__IMG:landscape__','春景中的青山'],water:['__IMG:landscape__','春景中的河水']};
  const svg='http://www.w3.org/2000/svg';
  let level=0, active, stroke=0, segments=[], pointer=null, last=null, demo=false, finished=false, misses=0, stepTimer;
  let gestureMarked=false, gestureCompleted=false;
  function shape(tag,attrs){
    const node=document.createElementNS(svg,tag);
    for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);
    paths.appendChild(node);return node;
  }
  function render(key){
    clearTimeout(stepTimer);active=key;stroke=0;clearPointer();misses=0;finished=false;
    show.disabled=demo;redo.disabled=true;
    paths.replaceChildren();word.textContent=glyphs[key][0];
    const visual=pictures[key];
    aside.dataset.picture=String(Boolean(visual));
    picture.hidden=!visual;
    if(visual){[picture.src,picture.alt]=visual}
    else{picture.removeAttribute('src');picture.alt=''}
    segments=glyphs[key][1].map(d=>{
      const guide=shape('path',{d,class:'ink-guide'}),ink=shape('path',{d,class:'ink-overlay',visibility:'hidden'});
      const length=guide.getTotalLength(), count=Math.max(8,Math.ceil(length/2));
      return {guide,ink,points:Array.from({length:count},(_,i)=>guide.getPointAtLength(i*length/(count-1))),covered:new Set(),dots:[]};
    });
    segments[0].guide.classList.add('current');
  }
  function clearPointer(){pointer=null;last=null;gestureMarked=false;gestureCompleted=false}
  function fillStroke(){
    const current=segments[stroke];if(!current)return;
    current.guide.classList.remove('current');current.ink.setAttribute('visibility','visible');
    for(const dot of current.dots)dot.remove();
    stroke++;misses=0;
    if(segments[stroke])segments[stroke].guide.classList.add('current');
    else if(!demo)complete();
  }
  function complete(){
    if(finished)return;
    finished=true;show.disabled=true;redo.disabled=true;clearPointer();
    K.sfx.ok();K.star(1,grid);K.levels(rounds.length,level+1);
    K.say('这一格练完了。纸笔表现请大人看。','ok');
    stepTimer=setTimeout(()=>{
      level++;
      if(level<rounds.length){render(rounds[level]);return}
      K.finish({title:'田字格练完啦',sub:'纸上再写一次，请大人看看。',again:reset});
    },1000);
  }
  function mark(x,y){
    const current=segments[stroke];if(!current||gestureCompleted)return;
    current.points.forEach((p,i)=>{
      if(!current.covered.has(i)&&Math.hypot(p.x-x,p.y-y)<4.1){
        current.covered.add(i);gestureMarked=true;
        current.dots.push(shape('circle',{cx:p.x,cy:p.y,r:1.9,fill:'#38775c'}));
      }
    });
    if(current.covered.size/current.points.length>=0.78){
      gestureCompleted=true;
      K.sfx.tick(stroke);
      fillStroke();
      if(!finished)K.say('这一笔留下了颜色。再看下一笔。','ok');
    }
  }
  function where(e){
    const r=grid.getBoundingClientRect();
    return {x:(e.clientX-r.left)*100/r.width,y:(e.clientY-r.top)*100/r.height};
  }
  grid.addEventListener('pointerdown',e=>{
    if(demo||finished||pointer!==null||(e.pointerType==='mouse'&&e.button!==0))return;
    e.preventDefault();pointer=e.pointerId;grid.setPointerCapture?.(pointer);last=where(e);mark(last.x,last.y);
  });
  grid.addEventListener('pointermove',e=>{
    if(pointer!==e.pointerId||!last)return;
    const next=where(e), start=last, count=Math.max(1,Math.ceil(Math.hypot(next.x-start.x,next.y-start.y)/1.5));
    if(count>2)redo.disabled=false;
    for(let i=1;i<=count;i++){if(pointer===null)break;mark(start.x+(next.x-start.x)*i/count,start.y+(next.y-start.y)*i/count)}
    if(pointer!==null)last=next;
  });
  function lift(e){
    if(pointer!==e.pointerId)return;
    const marked=gestureMarked;
    clearPointer();
    if(!marked&&!finished&&e.type==='pointerup'){
      misses++;K.say(misses===1?'沿浅色线慢慢描。':'可以点右边的小箭头，看下一笔。','no');K.sfx.no();
      if(misses>=3)K.highlight('#ink-show');
    }
  }
  grid.addEventListener('pointerup',lift);grid.addEventListener('pointercancel',lift);
  show.onclick=()=>{if(!demo&&!finished){K.sfx.pick();K.say('看一笔，再试着描。');fillStroke()}};
  redo.onclick=()=>{if(!demo&&!finished){K.sfx.pick();render(active);K.say('这一格从头再练。')}};
  function reset(){demo=false;level=0;K.stars=0;K.$('#star-n').textContent='0';K.levels(rounds.length,0);render(rounds[0]);K.say('沿浅色线描。也可以点小箭头看。')}
  function teach(key){
    demo=true;render(key);K.say('');
    const step=()=>{fillStroke();if(stroke<segments.length)stepTimer=setTimeout(step,380)};
    stepTimer=setTimeout(step,240);
  }
  picture.addEventListener('error',()=>{picture.hidden=true;aside.dataset.picture='false'});
  K.hud({icon:'◇',title:'田字格',levels:rounds.length});K.owl();K.onStart=reset;
  K.onState=state=>{
    if(state.inkDemo==='practice')reset();
    else if(rounds.includes(state.inkDemo))teach(state.inkDemo);
  };
  K.ready({emoji:'◇',title:document.title,sub:'先看笔画，再慢慢描。'});
})();

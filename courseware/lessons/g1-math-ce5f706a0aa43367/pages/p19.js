(function(root){
'use strict';
const C=['#D8845F','#70A78B','#E6B95F'];
const rules={
 count:(marked,total,answer)=>marked===total&&answer===total,
 taller:(heights,aligned,index)=>aligned.every(Boolean)&&heights[index]===Math.max(...heights),
 longer:(lengths,aligned,straight,index)=>aligned.every(Boolean)&&straight.every(Boolean)&&lengths[index]===Math.max(...lengths),
 more:(top,bottom,pairs,side)=>pairs===Math.min(top,bottom)&&side===(top===bottom?'equal':top>bottom?'top':'bottom'),
 larger:(widths,aligned,index)=>aligned&&widths[index]===Math.max(...widths),
 fit:(candidate,hole)=>candidate.shape===hole.shape&&candidate.size===hole.size,
 hidden:(total,visible)=>{if(!Number.isInteger(total)||!Number.isInteger(visible)||visible<0||visible>total)throw Error('invalid clue');return total-visible;},
 sort:(item,bin)=>({book:'book',notebook:'notebook',pencil:'pencil-case'})[item]===bin,
 ordered:a=>a.length===3&&a.every(Number.isFinite)&&a[0]>a[1]&&a[1]>a[2]
};
function shape(k,color=C[0],size=150){
 let b=k==='circle'?'<circle cx="100" cy="100" r="83"/>':k==='triangle'?'<path d="M100 15 L185 180 L15 180 Z"/>':'<rect x="18" y="'+(k==='rectangle'?45:18)+'" width="164" height="'+(k==='rectangle'?110:164)+'" rx="4"/>';
 return '<svg width="'+size+'" height="'+size+'" viewBox="0 0 200 200" aria-hidden="true"><g fill="'+color+'" stroke="#6B4423" stroke-width="5">'+b+'</g></svg>';
}
function solid(k,size=160){
 let b=k==='circle'?'<path d="M30 55 V155 A70 25 0 0 0 170 155 V55" fill="#70A78B"/><ellipse cx="100" cy="55" rx="70" ry="25" fill="#AED3BD"/><path d="M30 155 A70 25 0 0 0 170 155" fill="none"/>':k==='square'?'<path d="M30 60 L65 25 H180 L145 60 Z" fill="#EBC7AA"/><path d="M145 60 L180 25 V140 L145 175 Z" fill="#B96648"/><rect x="30" y="60" width="115" height="115" fill="#D8845F"/>':'<path d="M15 85 L55 45 H185 L145 85 Z" fill="#F1D898"/><path d="M145 85 L185 45 V130 L145 170 Z" fill="#B68E3D"/><rect x="15" y="85" width="130" height="85" fill="#E6B95F"/>';
 return '<svg width="'+size+'" height="'+size+'" viewBox="0 0 210 210" aria-hidden="true"><g stroke="#6B4423" stroke-width="4" stroke-linejoin="round">'+b+'</g></svg>';
}
function dots(n,color=C[0],w=36){return '<span class="garden-quantity">'+Array.from({length:n},()=>'<i style="width:'+w+'px;height:'+w+'px;background:'+color+'"></i>').join('')+'</span>';}
function mount(cfg){
 const K=root.K,D=root.document,stage=K.$('#garden-work'),anchor=K.$('#garden-anchor'),choices=K.$('#garden-choices');
 let st,serial=0,selected=null,controlCounter=0;
 const imgs={pot:'__IMG:pot__',book:'__IMG:book__',notebook:'__IMG:notebook__',pencil:'__IMG:pencil__','pencil-case':'__IMG:pencil-case__',backpack:'__IMG:backpack__'};
 function pic(k,alt='',size=150){return '<img class="garden-picture" src="'+imgs[k]+'" alt="'+alt+'" style="width:'+size+'px;height:'+size+'px" draggable="false">';}
 function reset(){serial++;st={level:0,misses:0,demo:false,show:false,hint:0,busy:false};selected=null;K.stars=0;const star=K.$('#star-n');if(star)star.textContent='0';init();}
 function current(){return st.demo?(st.demoValue??cfg.demo):cfg.levels[st.level];}
 function init(){st.marked=[];st.aligned=[false,false];st.straight=[true,false];st.pairs=[];st.overlay=false;st.revealed=false;st.guess=0;st.placed={};st.slots=[null,null,null];st.attemptPrint=null;selected=null;st.busy=false;K.$('#garden-stage').classList.remove('teach-hl');K.say('');render();}
 function button(parent,html,fn,cls='',label='操作'){let b=K.el('button','garden-button '+cls,html,parent);b.type='button';b.id='garden-control-'+(++controlCounter);b.setAttribute('aria-label',label);b.addEventListener('click',()=>{if(b._gardenSkipClick){b._gardenSkipClick=false;return;}if(!st.busy&&!st.demo)fn(b);});return b;}
 function drag(el,targets,fn){K.drag(el,{enabled:()=>!st.busy&&!st.demo,targets:()=>targets.filter(Boolean),onTap:()=>{el.click();el._gardenSkipClick=true;setTimeout(()=>{el._gardenSkipClick=false;},0);},onDrop:(_,t)=>{el._gardenSkipClick=true;setTimeout(()=>{el._gardenSkipClick=false;},0);if(t)fn(t);else fail(el);}});}
 function clear(){controlCounter=0;stage.innerHTML='';anchor.innerHTML='';choices.innerHTML='';stage.className='garden-work '+cfg.mode;anchor.className='garden-anchor '+cfg.mode;K.drags=[];K.levels(cfg.levels.length,st.level);}
 function win(el){if(st.busy||st.demo)return;st.busy=true;K.$('#garden-stage').classList.remove('teach-hl');stage.classList.remove('garden-hint-one','garden-hint-two');anchor.classList.remove('garden-hint-two');choices.classList.remove('garden-hint-two');stage.querySelectorAll('.garden-observe').forEach(x=>x.classList.remove('garden-observe'));K.sfx.ok();K.star(1,el);K.say('这次操作完成了。','ok');const stamp=serial;setTimeout(()=>{if(stamp!==serial)return;st.level++;st.misses=0;st.hint=0;if(st.level===cfg.levels.length){K.finish({title:'完成这一站',sub:'把方法说给大人听，口述表现待观察。',again:reset});}else init();},650);}
 function fail(el){if(st.busy||st.demo)return;st.misses++;st.hint=Math.min(3,st.misses);K.sfx.no();K.shake(el);K.say(st.misses===1?'先看看需要比较的地方，再试一次。':'把边缘、起点或没有配上的部分看清楚。','no');if(st.misses<3){K.highlight('#garden-stage');render();return;}st.busy=true;const stamp=serial;st.show=true;render();setTimeout(()=>{if(stamp!==serial)return;st.show=false;st.misses=0;st.hint=0;init();},1600);}
 function act(fn){return ()=>{if(!st.busy&&!st.demo)fn();};}
 function render(){
  clear();const v=current(),show=st.show;
  if(cfg.mode==='count'){
   let box=K.el('div','garden-pots',null,stage);const seen=show||st.demoMarks?Array.from({length:show?v:st.demoMarks},(_,i)=>i):st.marked;
   for(let i=0;i<v;i++){let b=button(box,pic('pot','盆栽',145),()=>{if(st.marked.includes(i))return;st.marked.push(i);K.sfx.tick(st.marked.length);render();},'garden-pot'+(seen.includes(i)?' marked':''),'给这一盆做记号');if(seen.includes(i))b.insertAdjacentHTML('beforeend','<span class="garden-check">✓</span>');}
   anchor.innerHTML='<div class="garden-count-line" aria-hidden="true">'+dots(seen.length,C[1],25)+'</div>';
   const answers=cfg.answers[st.demo?0:st.level];answers.forEach(n=>{const option=button(choices,dots(n,C[0],22),b=>rules.count(st.marked.length,v,n)?win(b):fail(b),'garden-count-option','选择'+n+'个数量点');option.disabled=!show&&st.marked.length!==v;});
  }else if(cfg.mode==='shape'||cfg.mode==='print'||cfg.mode==='fit'){
   const target=typeof v==='string'?v:v.shape;const hole={shape:target,size:150};
   anchor.innerHTML='<div class="garden-target" data-hit="true">'+shape(target,'#FFFDF6',cfg.mode==='print'?185:150)+'</div>';let targetEl=anchor.firstElementChild;targetEl.id='garden-drop';
   let opts=cfg.mode==='shape'?cfg.options.map(shape=>({shape,size:150})):cfg.mode==='print'?['square','circle','rectangle'].map(shape=>({shape,size:150})):[{shape:target,size:210},{shape:['circle','square','triangle'].find(x=>x!==target),size:150},{shape:target,size:150}];
   if(cfg.mode==='print'&&st.attemptPrint&&!show)targetEl.insertAdjacentHTML('beforeend','<span class="garden-try-print" aria-label="刚才印出的形状">'+shape(st.attemptPrint,C[2],160)+'</span>');
   const choose=(o,b)=>{if(cfg.mode==='fit'?!rules.fit(o,hole):o.shape!==target){if(cfg.mode==='print')st.attemptPrint=o.shape;fail(b);return;}b.classList.add('placed');b.disabled=true;b.style.visibility='hidden';targetEl.innerHTML=shape(target,C[1],cfg.mode==='print'?185:150);win(targetEl);};
   opts.forEach((o,i)=>{let b=button(stage,cfg.mode==='print'?solid(o.shape,185):shape(o.shape,C[i%3],o.size),()=>{selected=i;K.sfx.pick();render();},'garden-shape-option'+(selected===i?' selected':''),'选择一块图形');b.dataset.choice=String(i);drag(b,[targetEl],()=>choose(o,b));});
   targetEl.addEventListener('click',act(()=>{if(selected!==null){let b=stage.querySelector('[data-choice="'+selected+'"]');choose(opts[selected],b);}}));
   if(show){targetEl.innerHTML=shape(target,C[1],cfg.mode==='print'?185:150);stage.querySelectorAll('button').forEach(b=>b.classList.remove('selected'));}
   choices.innerHTML='<div class="garden-action-cue" aria-hidden="true">'+'↑'+'</div>';
  }else if(cfg.mode==='height'||cfg.mode==='length'){
   const vertical=cfg.mode==='height';anchor.innerHTML=vertical?'<div class="garden-floor" id="garden-floor"></div>':'<div class="garden-startline" id="garden-floor"></div>';let floor=anchor.firstElementChild;
   for(let i=0;i<2;i++){
    let aligned=st.aligned[i]||show,straight=st.straight[i]||show||vertical;
    let html=vertical?'<div class="garden-tower" style="height:'+v[i]+'px;background:'+C[i]+'"></div>':straight?'<div class="garden-ribbon" style="width:'+v[i]+'px;background:'+C[i]+'"></div>':'<svg width="'+(2*Math.sqrt(v[i]*v[i]/4-2500)+36)+'" height="110" viewBox="0 0 '+(2*Math.sqrt(v[i]*v[i]/4-2500)+36)+' 110"><path d="M18 25 L'+(18+Math.sqrt(v[i]*v[i]/4-2500))+' 75 L'+(18+2*Math.sqrt(v[i]*v[i]/4-2500))+' 25" stroke="'+C[i]+'" stroke-width="34" fill="none"/></svg>';
    let b=button(stage,html,()=>{if(!st.aligned[i]){st.aligned[i]=true;K.sfx.drop();render();return;}if(vertical?rules.taller(v,st.aligned,i):rules.longer(v,st.aligned,st.straight,i))win(b);else fail(b);},vertical?'garden-tower-wrap':'garden-ribbon-wrap','移动后选择这个对象');b.style.left=(vertical?280+i*460:aligned?127:255+i*100)+'px';b.style.top=(vertical?400-v[i]-(aligned?0:20+i*10):100+i*190)+'px';
    drag(b,[floor],()=>{st.aligned[i]=true;K.sfx.drop();render();});
   }
   if(!vertical)button(choices,'<svg width="68" height="44" viewBox="0 0 100 50"><path d="M5 25 C30 0 65 50 95 25 M5 44 H95" fill="none" stroke="#6B4423" stroke-width="5"/></svg>',()=>{st.straight=[true,true];K.sfx.pick();render();},'','拉直弯曲的丝带');
  }else if(cfg.mode==='pair'){
   const a=v[0],b=v[1];let top=K.el('div','garden-dotrow top',null,stage),bottom=K.el('div','garden-dotrow bottom',null,stage);
   function connect(i,j){if(st.pairs.some(p=>p[0]===i||p[1]===j))return;st.pairs.push([i,j]);selected=null;K.sfx.drop();render();}
   for(let i=0;i<a;i++){let paired=show?i<Math.min(a,b):st.pairs.some(p=>p[0]===i);let el=button(top,shape('circle',C[0],84),()=>{if(paired)return;selected=i;render();},(paired?' paired':'')+(selected===i?' selected':''),'选上排一个数量点');el.dataset.index=i;}
   for(let j=0;j<b;j++){let paired=show?j<Math.min(a,b):st.pairs.some(p=>p[1]===j);let el=button(bottom,shape('circle',C[1],84),()=>{if(selected!==null&&!paired)connect(selected,j);},paired?'paired':'','给它找下排伙伴');el.dataset.index=j;}
   Array.from(top.children).forEach((el,i)=>drag(el,Array.from(bottom.children),target=>connect(i,Number(target.dataset.index))));
   const pairs=show?Array.from({length:Math.min(a,b)},(_,i)=>[i,i]):st.pairs;
   const origin=anchor.getBoundingClientRect(),scale=K.scale||1;
   const center=el=>{const r=el.getBoundingClientRect();return [(r.left+r.width/2-origin.left)/scale,(r.top+r.height/2-origin.top)/scale];};
   anchor.innerHTML='<svg width="1100" height="435" viewBox="0 0 1100 435">'+pairs.map(([i,j])=>{const [x1,y1]=center(top.children[i]),[x2,y2]=center(bottom.children[j]);return '<line x1="'+x1+'" y1="'+y1+'" x2="'+x2+'" y2="'+y2+'" stroke="#A79A83" stroke-width="7"/>';}).join('')+'</svg>';
   [['↑','top'],['=','equal'],['↓','bottom']].forEach(([icon,side])=>{const choice=button(choices,icon,el=>rules.more(a,b,st.pairs.length,side)?win(el):fail(el),'garden-row-choice','选择'+side);choice.disabled=!show&&st.pairs.length<Math.min(a,b);});
  }else if(cfg.mode==='size'){
   let aligned=st.overlay||show;anchor.innerHTML='<button class="garden-corner" type="button" aria-label="对齐这个角">⌞<span class="garden-corner-dot" aria-hidden="true"></span></button>';const corner=anchor.firstElementChild;corner.id='garden-corner';corner.addEventListener('click',act(()=>{st.overlay=true;render();}));
   v.forEach((w,i)=>{let el=button(stage,'',()=>{if(!st.overlay){st.overlay=true;K.sfx.drop();render();}else rules.larger(v,st.overlay,i)?win(el):fail(el);},'garden-paper','重叠比较这张纸');el.style.cssText='left:'+(i===0||aligned?160:730)+'px;top:'+(420-w*0.65)+'px;width:'+w+'px;height:'+(w*0.65)+'px;background:'+C[i]+';opacity:.72;z-index:'+i;el.disabled=aligned;drag(el,[corner],()=>{st.overlay=true;K.sfx.drop();render();});});
   v.forEach((w,i)=>button(choices,shape('rectangle',C[i],w/5),el=>rules.larger(v,st.overlay,i)?win(el):fail(el),'garden-paper-choice','选择这张纸更大'));
  }else if(cfg.mode==='infer'){
   const total=v[0],known=v[1];anchor.innerHTML='<div class="garden-total">'+dots(total,C[2],44)+'</div>';
   let left=button(stage,st.revealed||show?dots(known,C[0],55):'<svg width="90" height="64" viewBox="0 0 100 65"><path d="M5 32 Q50 -15 95 32 Q50 80 5 32Z" fill="#FFFDF6" stroke="#6B4423" stroke-width="5"/><circle cx="50" cy="32" r="14" fill="#6B4423"/></svg>',()=>{st.revealed=true;K.sfx.pick();render();},'garden-container left','揭开左边容器');
   left.id='garden-peek';let right=K.el('div','garden-container right',null,stage);right.id='garden-hidden';right.setAttribute('aria-label','重建右边容器的数量');
   const count=show?rules.hidden(total,known):st.guess;for(let j=0;j<count;j++){let chip=button(right,shape('circle',C[2],76),()=>{if(st.revealed){st.guess--;render();}},'garden-hidden-dot','把这个点取回来');chip.id='garden-hidden-dot-'+(j+1);}
   for(let j=0;j<total;j++){let chip=button(choices,shape('circle',C[2],72),()=>{if(!st.revealed){fail(left);return;}if(st.guess<total){st.guess++;K.sfx.drop();render();}},'','给右边放一个点');chip.id='garden-reserve-'+(j+1);chip.disabled=!st.revealed&&!show;}
   let confirm=button(choices,'✓',el=>{if(!st.revealed||st.guess!==rules.hidden(total,known)){fail(el);return;}right.classList.add('garden-verified');win(right);},'garden-confirm','揭开验证');confirm.id='garden-check-count';confirm.disabled=!st.revealed&&!show;
  }else if(cfg.mode==='sort'){
   const list=v;const bins=['book','notebook','pencil-case'];
   list.forEach((item,i)=>{if(st.placed[i]||show)return;let el=button(stage,pic(item,item,155),()=>{selected=i;render();},'garden-sort-item'+(selected===i?' selected':''),'选择需要归位的物品');el.style.left=(200+i*285)+'px';el.dataset.index=i;});
   bins.forEach((bin,j)=>{let holder=button(choices,pic(bin,bin,96),el=>{if(selected===null)return;if(!rules.sort(list[selected],bin)){fail(el);return;}st.placed[selected]=bin;selected=null;K.sfx.drop();const complete=Object.keys(st.placed).length===list.length;render();if(complete)win(choices.querySelector('[data-bin="'+bin+'"]'));},'garden-bin','归入这个图示的收纳处');holder.dataset.bin=bin;const placed=show?list.filter(item=>rules.sort(item,bin)):Object.keys(st.placed).filter(i=>st.placed[i]===bin).map(i=>list[i]);if(placed.length)holder.insertAdjacentHTML('beforeend','<span class="garden-stored">'+placed.map(item=>pic(item,'已归位',52)).join('')+'</span>');});
   stage.querySelectorAll('button').forEach(el=>drag(el,Array.from(choices.children),bin=>{selected=Number(el.dataset.index);bin.click();}));
   anchor.innerHTML='<div class="garden-sort-desk"></div>';
  }else if(cfg.mode==='books'){
   anchor.innerHTML='<div class="garden-book-bag">'+pic('backpack','书包',120)+'</div>';let slots=K.el('div','garden-slots',null,stage);
   const next=st.slots.findIndex(x=>x===null);
   function place(i,size,el){if(i!==next||size===null)return;const remaining=v.filter(n=>!st.slots.includes(n));if(size!==Math.max(...remaining)){selected=null;fail(el);return;}st.slots[i]=size;selected=null;K.sfx.drop();render();}
   for(let i=0;i<3;i++){const value=show?[190,145,100][i]:st.slots[i];let el=button(slots,value?pic('book','已放入的书',value):'<span class="garden-slot-outline"></span>',el=>place(i,selected,el),'garden-book-slot'+(!show&&i===next?' current':''),'第'+(i+1)+'个大小排序位置');el.dataset.slot=i;el.disabled=show||i!==next;}
   v.forEach(size=>{if(st.slots.includes(size)||show)return;let el=button(choices,pic('book','待排列的书',size*.6),()=>{selected=size;render();},'garden-book-option'+(selected===size?' selected':''),'选择一本待排序的书');el.id='garden-book-'+size;drag(el,Array.from(slots.children).filter(slot=>!slot.disabled),slot=>place(Number(slot.dataset.slot),size,slot));});
   const confirm=button(choices,'✓',el=>rules.ordered(st.slots)?win(el):fail(el),'garden-confirm','检查从大到小的顺序');confirm.id='garden-check-order';confirm.disabled=next!==-1&&!show;
  }
  if(st.hint===1)stage.classList.add('garden-hint-one');
  if(st.hint===2){
   stage.classList.add('garden-hint-two');anchor.classList.add('garden-hint-two');choices.classList.add('garden-hint-two');
   if(cfg.mode==='count')stage.querySelectorAll('.garden-pot:not(.marked)').forEach(el=>el.classList.add('garden-observe'));
   if(cfg.mode==='pair')stage.querySelectorAll('.garden-dotrow button:not(.paired)').forEach(el=>el.classList.add('garden-observe'));
  }else choices.classList.remove('garden-hint-two');
  if(show){
   let answer=null;
   if(cfg.mode==='count')answer=Array.from(choices.querySelectorAll('button')).find(el=>el.getAttribute('aria-label')==='选择'+v+'个数量点');
   if(cfg.mode==='height'||cfg.mode==='length')answer=stage.querySelectorAll('button')[v[0]>v[1]?0:1];
   if(cfg.mode==='pair')answer=choices.querySelectorAll('button')[v[0]===v[1]?1:v[0]>v[1]?0:2];
   if(cfg.mode==='size')answer=choices.querySelectorAll('button')[v[0]>v[1]?0:1];
   if(cfg.mode==='infer')answer=stage.querySelector('.garden-container.right');
   if(answer)answer.classList.add('garden-demo-answer');
  }
  K.$$('#garden-stage img, #garden-choices img').forEach(im=>im.addEventListener('error',()=>{im.classList.add('garden-image-error');im.alt='图片未加载，请点圆形箭头重试';st.busy=true;}));
 }
 K.hud({icon:'○',title:cfg.title,levels:cfg.levels.length});K.owl();K.onStart=reset;
 K.onState=function(state){if(state.phase==='demo'){reset();st.demo=true;init();}else if(state.phase==='count'&&st.demo&&cfg.mode==='count'&&Number.isInteger(state.marks)&&state.marks>=1&&state.marks<=current()){st.demoMarks=state.marks;st.show=state.marks===current();render();}else if(state.phase==='show'){if(st.demo&&state.example&&Object.prototype.hasOwnProperty.call(cfg.demoExamples||{},state.example))st.demoValue=cfg.demoExamples[state.example];st.show=true;render();}else if(state.phase==='play'){reset();}};
 const resetControl=K.$('#garden-reset');K.stage().appendChild(resetControl);resetControl.style.top='98px';resetControl.style.right='38px';resetControl.addEventListener('click',()=>{serial++;if(st.demo)return;const n=st.level,stars=K.stars;reset();st.level=n;K.stars=stars;const badge=K.$('#star-n');if(badge)badge.textContent=String(stars);init();});
 K.ready({emoji:'○',title:cfg.title,sub:'听小数老师讲，再动手试一试。'});reset();
 root.GardenDebug={state:()=>JSON.parse(JSON.stringify(st)),config:cfg,reset};
}
const api={rules,shape,solid,mount};if(typeof module==='object'&&module.exports)module.exports=api;else root.Garden=api;
})(typeof window!=='undefined'?window:globalThis);

Garden.mount({"mode":"infer","demo":[1,0],"levels":[[1,0],[2,1],[2,2]],"title":"看一边摆另一边","demoExamples":{"two":[2,1]}});

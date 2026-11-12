const supplies = {
  2:"__IMG:quantity-2__",6:"__IMG:quantity-6__",20:"__IMG:quantity-20__",
  3:"__IMG:quantity-3__",4:"__IMG:quantity-4__",30:"__IMG:quantity-30__",40:"__IMG:quantity-40__",
  34:"__IMG:quantity-34__",43:"__IMG:quantity-43__",25:"__IMG:quantity-25__",52:"__IMG:quantity-52__"
};
const stations={green:"__IMG:station-leaf__",sun:"__IMG:station-sun__",flower:"__IMG:station-flower__"};
const orders = {
  2:  {original:46,before:"__IMG:before-46__",remainder:"__IMG:remaining-44__"},
  6:  {original:58,before:"__IMG:before-58__",remainder:"__IMG:remaining-52__"},
  30: {original:65,before:"__IMG:before-65__",remainder:"__IMG:remaining-35__"},
  40: {original:82,before:"__IMG:before-82__",remainder:"__IMG:remaining-42__"},
  34: {original:76,before:"__IMG:before-76__",remainder:"__IMG:remaining-42__"},
  25: {original:68,before:"__IMG:before-68__",remainder:"__IMG:remaining-43__"},
  43: {original:97,before:"__IMG:before-97__",remainder:"__IMG:remaining-54__"}
};
const cards=new Map();
for (const path of [...Object.values(supplies),...Object.values(stations),...Object.values(orders).flatMap(({before,remainder})=>[before,remainder])]) {
  if (cards.has(path)) continue;
  const image=new Image();
  image.src=path;
  cards.set(path,image);
}
const cues=steps=>({goal:steps[0],steps,hint:"truck-hint",hint2:"truck-help",praise:"truck-praise"});
const hints=["再听是整盘、散盆，还是都有。","看亮起的数量图，停稳再按方键。"];

K.ready({title:"开车送走指定的一份",sub:"听清取走几盘几盆。按方键装货，再开去指定的站。"});

const options=K.gameTemplates.listenDelivery({
  voiceLead:true, stepVoiceLead:true,
  cues:[
    cues(["take-2","to-green","take-6","to-sun"]),
    cues(["take-30","to-flower","take-40","to-green"]),
    cues(["take-34","to-sun","take-25","to-flower","take-43","to-green"])
  ],
  art:{backdrop:"__IMG:seedling-delivery-yard__",frames:["__IMG:seedling-cart__","__IMG:seedling-cart__","__IMG:seedling-traffic__"],
    sticker:"__IMG:seedling-badge__",icons:{...supplies,...stations}},
  doneText:"送走的和剩下的都数清了！",
  levels:[
    {pickup:[[2,4],[20,2],[6,6]],drop:[["green",4],["sun",2]],orders:[[2,"green"],[6,"sun"]],
      lanes:[{row:2,speed:.72,spacing:5.7,phase:1.3}],step:.35,hints},
    {pickup:[[30,4],[3,2],[40,6],[4,8]],drop:[["flower",2],["green",4],["sun",7]],orders:[[30,"flower"],[40,"green"]],
      lanes:[{row:1,speed:.88,spacing:5.1,phase:1.6},{row:3,speed:-1.14,spacing:4.9,phase:2.2}],step:.30,hints},
    {pickup:[[34,2],[43,4],[25,6],[52,8]],drop:[["sun",1],["flower",4],["green",7]],orders:[[34,"sun"],[25,"flower"],[43,"green"]],
      lanes:[{row:1,speed:1.2,spacing:4.9,phase:2.2},{row:2,speed:-1.35,spacing:4.6,phase:.4},{row:3,speed:1.47,spacing:4.9,phase:1.5}],step:.26,hints}
  ]
});

function panel(c,x,y,w,h,colour) {
  c.fillStyle=colour;
  K.draw.rr(c,x,y,w,h,13);
  c.fill();
}

function card(c,path,x,y,w,h,highlighted,fallback) {
  panel(c,x,y,w,h,highlighted?"#ffcb6c":"#537465");
  panel(c,x+6,y+6,w-12,h-12,"#fff2d6");
  const art=cards.get(path);
  if (!art.naturalWidth) {
    if (fallback!==undefined) K.draw.text(c,String(fallback),x+w/2,y+h/2,33,"#2d5042");
    return;
  }
  const scale=Math.min((w-18)/art.naturalWidth,(h-18)/art.naturalHeight);
  const width=art.naturalWidth*scale;
  const height=art.naturalHeight*scale;
  c.drawImage(art,x+(w-width)/2,y+(h-height)/2,width,height);
}

const top=i=>101+i*119;
const draw=options.draw;
options.draw=(frame,c)=>{
  draw(frame,c);
  const {w:world,level}=frame.data;
  if (!world) return;
  const next=level.orders[world.order];
  level.pickup.forEach(([id],i)=>card(c,supplies[id],20,top(i),204,106,
    world.help&&world.carried===null&&next?.[0]===id,id));
  if (next) {
    const [id]=next;
    card(c,orders[id].before,1057,96,166,112,false,orders[id].original);
  }
  level.drop.forEach(([id],i)=>card(c,stations[id],1054+i*61,355,57,61,
    world.help&&world.carried!==null&&next?.[1]===id));
  const previous=level.orders[world.order-1];
  if (previous) {
    const [id]=previous;
    card(c,orders[id].remainder,1057,431,166,125,true,orders[id].original-id);
  }
};
options.onState=(_game,state)=>{
  if (state.demo===false) K.$$(".teach-hl").forEach(element=>element.classList.remove("teach-hl"));
};

const game=K.game(options);
game.follow("#first-removal-card",()=>({x:20,y:top(0),w:204,h:106}));
game.follow("#first-removal-bay",()=>({x:602,y:497,w:76,h:78}));

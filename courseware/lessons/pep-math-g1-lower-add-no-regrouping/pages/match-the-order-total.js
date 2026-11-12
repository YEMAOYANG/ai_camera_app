const orders = {
  "order-42-5":[42,5],"order-42-30":[42,30],"order-23-4":[23,4],
  "order-31-20":[31,20],"order-15-4":[15,4],"order-31-24":[31,24],
  "order-52-27":[52,27],"order-6-53":[6,53],"order-40-53":[40,53]
};
const totals=Object.fromEntries(Object.entries(orders).map(([id,[a,b]])=>[id,a+b]));
const formulas=Object.fromEntries(Object.entries(orders).map(([id,[a,b]])=>[id,a+" + "+b]));
const visualOrders = {
  "order-42-5":"__IMG:order-42-5__", "order-42-30":"__IMG:order-42-30__", "order-23-4":"__IMG:order-23-4__",
  "order-31-20":"__IMG:order-31-20__", "order-15-4":"__IMG:order-15-4__", "order-31-24":"__IMG:order-31-24__",
  "order-52-27":"__IMG:order-52-27__", "order-6-53":"__IMG:order-6-53__", "order-40-53":"__IMG:order-40-53__"
};
const orderTiles = {
  "order-42-5":"__IMG:tile-42-5__", "order-42-30":"__IMG:tile-42-30__", "order-23-4":"__IMG:tile-23-4__",
  "order-31-20":"__IMG:tile-31-20__", "order-15-4":"__IMG:tile-15-4__", "order-31-24":"__IMG:tile-31-24__",
  "order-52-27":"__IMG:tile-52-27__", "order-6-53":"__IMG:tile-6-53__", "order-40-53":"__IMG:tile-40-53__",
  47:"__IMG:total-47__",72:"__IMG:total-72__",27:"__IMG:total-27__",
  51:"__IMG:total-51__",19:"__IMG:total-19__",55:"__IMG:total-55__",
  79:"__IMG:total-79__",59:"__IMG:total-59__",93:"__IMG:total-93__"
};
const images=Object.fromEntries(Object.entries(visualOrders).map(([key,path])=>{
  const image=new Image();
  image.src=path;
  return [key,image];
}));
const hints=["再看有哪些十，哪些一。","先算同一单位，再找相合的数。"];
const cues=(steps)=>({goal:steps[0],steps,hint:"drop-hint",hint2:"drop-help",praise:"drop-praise"});
const level=(bottom,pieces,interval)=>({bottom,pieces,interval,hints,labels:formulas,
  matches:(order,total)=>totals[order]===total});

K.ready({title:"接住正确的总数",sub:"先听订单，看看整条和散贴。移动订单牌，让它落到正确总数旁。"});

const options=K.gameTemplates.fallingTiles({
  voiceLead:true, stepVoiceLead:true,
  cues:[
    cues(["drop-42-5","drop-42-30","drop-23-4"]),
    cues(["drop-31-20","drop-15-4","drop-31-24"]),
    cues(["drop-52-27","drop-6-53","drop-40-53"])
  ],
  art:{backdrop:"__IMG:tile-yard__",sticker:"__IMG:craft-sticker-badge__",icons:orderTiles},
  doneText:"每张订单都配上了正确的总数！",
  levels:[
    level([null,47,null,72,null,27],["order-42-5","order-42-30","order-23-4"],1.17),
    level([51,null,19,null,55,null],["order-31-20","order-15-4","order-31-24"],.90),
    level([null,79,null,59,null,93],["order-52-27","order-6-53","order-40-53"],.68)
  ]
});

const firstOrder={x:26,y:156,w:354,h:270};
const draw=options.draw;
options.draw=(frame,context)=>{
  draw(frame,context);
  const {w: world,level}=frame.data;
  if (!world) return;
  const key=level.pieces[world.i];
  if (!key) return;
  const {x,y,w,h}=firstOrder;
  context.fillStyle="#406653";
  K.draw.rr(context,x,y,w,h,18);
  context.fill();
  context.fillStyle="#fff2d7";
  K.draw.rr(context,x+7,y+7,w-14,h-14,14);
  context.fill();
  const image=images[key];
  if (image.naturalWidth) {
    const scale=Math.min((w-26)/image.naturalWidth,(h-38)/image.naturalHeight);
    const width=image.naturalWidth*scale;
    const height=image.naturalHeight*scale;
    context.drawImage(image,x+(w-width)/2,y+(h-height)/2,width,height);
  } else {
    K.draw.text(context,formulas[key],x+w/2,y+h/2,42,"#2b5143");
  }
};
options.onState=(_game,state)=>{
  if (state.demo===false) K.$$(".teach-hl").forEach((element)=>element.classList.remove("teach-hl"));
};

const game=K.game(options);
game.follow("#first-order-picture",()=>firstOrder);
game.follow("#first-tile-destination",()=>({x:500,y:526,w:140,h:70}));

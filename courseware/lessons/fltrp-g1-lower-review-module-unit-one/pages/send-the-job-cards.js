const workCards = {
  doctor: "__IMG:job-doctor__",
  nurse: "__IMG:job-nurse__",
  driver: "__IMG:job-driver__",
  teacher: "__IMG:job-teacher__"
};
const recipients = {
  nora: "__IMG:person-nora__",
  ming: "__IMG:person-ming__",
  lin: "__IMG:person-lin__",
  bo: "__IMG:person-bo__"
};
const icons = {...workCards, ...recipients};
const panels = Object.fromEntries(Object.entries(icons).map(([name, path]) => {
  const image = new Image();
  image.src = path;
  return [name, image];
}));
const hints = ["再听工作或名字，然后看图。", "看亮起来的卡，停车再按方键。"];
const cues = (steps) => ({goal: steps[0], steps, hint: "jobs-hint", hint2: "jobs-help", praise: "jobs-praise"});

K.ready({title: "送对职业图卡", sub: "听工作取卡，听名字送卡。用箭头开车，停稳点方键。"});

const options = K.gameTemplates.listenDelivery({
  voiceLead: true,
  stepVoiceLead: true,
  cues: [
    cues(["pick-doctor","send-nora","pick-nurse","send-ming"]),
    cues(["pick-driver","send-lin","pick-teacher","send-bo"]),
    cues(["pick-nurse","send-ming","pick-driver","send-lin","pick-teacher","send-bo"])
  ],
  art: {
    backdrop: "__IMG:community-game-yard__",
    frames: ["__IMG:community-cart__", "__IMG:community-cart__", "__IMG:community-traffic__"],
    sticker: "__IMG:community-star__",
    icons
  },
  doneText: "工作和人都配对了！",
  levels: [
    {
      pickup: [["doctor",4],["nurse",2],["teacher",6]],
      drop: [["nora",4],["ming",2]],
      orders: [["doctor","nora"],["nurse","ming"]],
      lanes: [{row:2,speed:.72,spacing:5.7,phase:1.3}],
      step:.35,
      hints
    },
    {
      pickup: [["driver",2],["teacher",4],["doctor",6],["nurse",8]],
      drop: [["lin",1],["bo",4],["nora",7]],
      orders: [["driver","lin"],["teacher","bo"]],
      lanes: [{row:1,speed:.88,spacing:5.1,phase:1.6},{row:3,speed:-1.14,spacing:4.9,phase:2.2}],
      step:.30,
      hints
    },
    {
      pickup: [["nurse",2],["teacher",4],["driver",6],["doctor",8]],
      drop: [["ming",1],["lin",4],["bo",7]],
      orders: [["nurse","ming"],["driver","lin"],["teacher","bo"]],
      lanes: [{row:1,speed:1.2,spacing:4.9,phase:2.2},{row:2,speed:-1.35,spacing:4.6,phase:.4},{row:3,speed:1.47,spacing:4.9,phase:1.5}],
      step:.26,
      hints
    }
  ]
});

function plate(c,x,y,w,h,colour) {
  c.fillStyle=colour;
  K.draw.rr(c,x,y,w,h,13);
  c.fill();
}

function paintCard(c,id,x,y,w,h,assisted) {
  plate(c,x,y,w,h,assisted?"#ffcc69":"#5c7c6a");
  plate(c,x+6,y+6,w-12,h-12,"#fff3dc");
  const art=panels[id];
  if (!art.naturalWidth) return;
  const scale=Math.min((w-18)/art.naturalWidth,(h-18)/art.naturalHeight);
  const width=art.naturalWidth*scale;
  const height=art.naturalHeight*scale;
  c.drawImage(art,x+(w-width)/2,y+(h-height)/2,width,height);
}

const rowTop = (i) => 100 + i * 119;
const draw=options.draw;
options.draw=(frame,canvas)=>{
  draw(frame,canvas);
  const {w: world,level}=frame.data;
  if (!world) return;
  const order=level.orders[world.order];
  level.pickup.forEach(([id],i)=>paintCard(canvas,id,20,rowTop(i),204,106,world.help&&world.carried===null&&id===order?.[0]));
  level.drop.forEach(([id],i)=>paintCard(canvas,id,1058+(i%2)*96,353+Math.floor(i/2)*98,90,92,world.help&&world.carried!==null&&id===order?.[1]));
};

options.onState=(_game,state)=>{
  if (state.demo===false) K.$$(".teach-hl").forEach((element)=>element.classList.remove("teach-hl"));
};

const game=K.game(options);
game.follow("#first-job-card",()=>({x:20,y:rowTop(0),w:204,h:106}));
game.follow("#first-pickup",()=>({x:602,y:497,w:76,h:78}));
game.follow("#job-replay",()=>{
  const button=K.$(".arc-voice");
  return button && button.offsetWidth ? K.pos(button) : null;
});

const bodyParts = {
  hands2: "__IMG:two-robot-hands__",
  hands3: "__IMG:three-robot-hands__",
  eyes2: "__IMG:two-robot-eyes__",
  eyes3: "__IMG:three-robot-eyes__",
  eyes4: "__IMG:four-robot-eyes__",
  ears2: "__IMG:two-robot-ears__",
  ears3: "__IMG:three-robot-ears__",
  feet2: "__IMG:two-robot-feet__",
  feet4: "__IMG:four-robot-feet__"
};
const pictures = Object.fromEntries(Object.entries(bodyParts).map(([id, path])=>{
  const image=new Image();
  image.src=path;
  return [id,image];
}));
const hints = ["听清问哪个部位，再点着数。", "对准亮起的图，推一推方向。"];
const cues = (steps) => ({goal: steps[0], steps, hint: "body-hint", hint2: "body-help", praise: "body-praise"});

const firstDrift=0;
const targetWidth=168;
const targetHeight=116;
const level=(targets,queue,drift,speed)=>({
  targets: targets.map(([x,value])=>({x,value})),
  queue,
  drift,
  speed,
  targetWidth,
  targetHeight,
  listenOnly:true,
  matches:(spoken,card)=>spoken===card,
  hints
});

K.ready({title: "把弹珠送到对应图", sub: "先听部位和数量，左右瞄准，点箭头发射。"});

const options=K.gameTemplates.magnetMarbles({
  voiceLead:true,
  stepVoiceLead:true,
  cues: [
    cues(["body-hands-two","body-eyes-three"]),
    cues(["body-ears-two","body-feet-four","body-eyes-two"]),
    cues(["body-hands-three","body-ears-three","body-feet-two","body-eyes-four"])
  ],
  art: {
    backdrop: "__IMG:community-marble-board__",
    frames: ["__IMG:community-marble__"],
    sticker: "__IMG:community-star__",
    icons: bodyParts
  },
  levels: [
    level([[392,"ears2"],[640,"hands2"],[888,"eyes3"]],["hands2","eyes3"],firstDrift,410),
    level([[334,"eyes2"],[538,"feet4"],[742,"ears2"],[946,"eyes4"]],["ears2","feet4","eyes2"],10,440),
    level([[334,"ears3"],[538,"hands3"],[742,"eyes4"],[946,"feet2"]],["hands3","ears3","feet2","eyes4"],19,490)
  ],
  doneText: "这组部位和数量都对！"
});
function drawPart(context,part,x,y) {
  context.strokeStyle="#284d42";
  context.fillStyle="#284d42";
  context.lineWidth=3;
  context.lineCap="round";
  if (part==="eyes") {
    context.beginPath();
    context.ellipse(x,y,12,8,0,0,Math.PI*2);
    context.stroke();
    K.draw.circle(context,x,y,4);
    return;
  }
  if (part==="ears") {
    context.beginPath();
    context.ellipse(x,y,8,13,.45,0,Math.PI*2);
    context.stroke();
    context.beginPath();
    context.arc(x-1,y+1,3,0,Math.PI*1.65);
    context.stroke();
    return;
  }
  if (part==="hands") {
    K.draw.rr(context,x-6,y-3,13,12,4);
    context.fill();
    for (const i of [-5,-2,1,4]) {
      context.beginPath();
      context.moveTo(x+i,y);
      context.lineTo(x+i,y-12+Math.abs(i)*.35);
      context.stroke();
    }
    context.beginPath();
    context.moveTo(x-5,y+4);
    context.lineTo(x-11,y-2);
    context.stroke();
    return;
  }
  context.beginPath();
  context.ellipse(x-1,y+2,6,11,.30,0,Math.PI*2);
  context.fill();
  for (let i=0;i<3;i++) K.draw.circle(context,x-1+i*4,y-9+i*2,2);
}

const draw=options.draw;
options.draw=(frame,context)=>{
  draw(frame,context);
  const {w: world,level}=frame.data;
  if (!world) return;
  context.save();
  for (const target of world.targets) {
    if (target.used || pictures[target.value].naturalWidth) continue;
    const count=Number(target.value.at(-1));
    const part=target.value.slice(0,-1);
    const center=target.x+Math.sin(world.time*2.4+target.x*.019)*level.drift;
    for (let i=0;i<count;i++) drawPart(context,part,center+(i-(count-1)/2)*31,229);
  }
  context.restore();
};

options.onState=(_game,state)=>{
  if (state.demo===false) K.$$(".teach-hl").forEach((element)=>element.classList.remove("teach-hl"));
};

const game=K.game(options);
game.follow("#first-body-target",()=>({x:640-targetWidth/2,y:229-targetHeight/2,w:targetWidth,h:targetHeight}));
game.follow("#body-cue",()=>{
  const button=K.$(".arc-voice");
  return button && button.offsetWidth ? K.pos(button) : null;
});

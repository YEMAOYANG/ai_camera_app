const problems={
  "diff-39-3":[39,3,"__IMG:problem-39-minus-3__"],
  "diff-46-30":[46,30,"__IMG:problem-46-minus-30__"],
  "diff-66-6":[66,6,"__IMG:problem-66-minus-6__"],
  "diff-66-60":[66,60,"__IMG:problem-66-minus-60__"],
  "diff-77-24":[77,24,"__IMG:problem-77-minus-24__"],
  "diff-86-25":[86,25,"__IMG:problem-86-minus-25__"],
  "diff-94-53":[94,53,"__IMG:problem-94-minus-53__"],
  "diff-68-23":[68,23,"__IMG:problem-68-minus-23__"]
};
const shots={
  "diff-39-3":"__IMG:shot-39-minus-3__", "diff-46-30":"__IMG:shot-46-minus-30__",
  "diff-66-6":"__IMG:shot-66-minus-6__", "diff-66-60":"__IMG:shot-66-minus-60__",
  "diff-77-24":"__IMG:shot-77-minus-24__", "diff-86-25":"__IMG:shot-86-minus-25__",
  "diff-94-53":"__IMG:shot-94-minus-53__", "diff-68-23":"__IMG:shot-68-minus-23__"
};
const targets={
  34:"__IMG:target-34__",36:"__IMG:target-36__",16:"__IMG:target-16__",57:"__IMG:target-57__",
  60:"__IMG:target-60__",6:"__IMG:target-6__",53:"__IMG:target-53__",45:"__IMG:target-45__",
  61:"__IMG:target-61__",41:"__IMG:target-41__",65:"__IMG:target-65__"
};
const images=Object.fromEntries(Object.entries(problems).map(([id,[a,b,path]])=>{
  const image=new Image();
  image.src=path;
  return [id,image];
}));
const labels=Object.fromEntries(Object.entries(problems).map(([id,[a,b]])=>[id,a+" − "+b]));
const hints=["再看从哪个单位里取。","对准发亮的图，再点发射。"];
const cues=(steps)=>({goal:steps[0],steps,hint:"marble-hint",hint2:"marble-help",praise:"marble-praise"});
const width=164, height=120;
const level=(targets,queue,drift,speed)=>({
  targets:targets.map(([x,value])=>({x,value})),queue,drift,speed,labels,hints,
  targetWidth:width,targetHeight:height,
  matches:(id,value)=>{
    const [original,removed]=problems[id];
    return original-removed===value;
  }
});

K.ready({title:"瞄准架上的剩余",sub:"听减式，看拿走的那份。左右瞄准表示余数的图，点发射。"});

const options=K.gameTemplates.magnetMarbles({
  voiceLead:true, stepVoiceLead:true,
  cues:[
    cues(["diff-39-3","diff-46-30"]),
    cues(["diff-66-6","diff-66-60","diff-77-24"]),
    cues(["diff-86-25","diff-94-53","diff-68-23"])
  ],
  art:{backdrop:"__IMG:seedling-marble-yard__",frames:["__IMG:seedling-marble__"],sticker:"__IMG:seedling-badge__",icons:{...shots,...targets}},
  doneText:"每一份剩余都找对了！",
  levels:[
    level([[392,34],[640,36],[888,16]],["diff-39-3","diff-46-30"],0,410),
    level([[334,57],[538,60],[742,6],[946,53]],["diff-66-6","diff-66-60","diff-77-24"],10,440),
    level([[334,45],[538,61],[742,41],[946,65]],["diff-86-25","diff-94-53","diff-68-23"],19,490)
  ]
});

const position={x:17,y:237,w:192,h:290};
const draw=options.draw;
options.draw=(frame,c)=>{
  draw(frame,c);
  const {w:world,level}=frame.data;
  if (!world) return;
  const id=level.queue[world.i];
  if (!id) return;
  const {x,y,w,h}=position;
  c.fillStyle="#416956";
  K.draw.rr(c,x,y,w,h,15);
  c.fill();
  c.fillStyle="#fff2d7";
  K.draw.rr(c,x+6,y+6,w-12,h-12,12);
  c.fill();
  const image=images[id];
  if (!image.naturalWidth) {
    K.draw.text(c,labels[id],x+w/2,y+h/2,32,"#2c5342");
    return;
  }
  const scale=Math.min((w-20)/image.naturalWidth,(h-24)/image.naturalHeight);
  const iw=image.naturalWidth*scale,ih=image.naturalHeight*scale;
  c.drawImage(image,x+(w-iw)/2,y+(h-ih)/2,iw,ih);
};
options.onState=(_game,state)=>{
  if (state.demo===false) K.$$(".teach-hl").forEach(element=>element.classList.remove("teach-hl"));
};

const game=K.game(options);
game.follow("#first-remain-problem",()=>position);
game.follow("#first-remain-target",()=>({x:640-width/2,y:229-height/2,w:width,h:height}));

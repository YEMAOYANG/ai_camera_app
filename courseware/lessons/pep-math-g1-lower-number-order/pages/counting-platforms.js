K.ready({title:'沿票号跳',sub:'看箭头，先听数法。落在紧接着的票号上。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:build-first-two-rows__';},{once:true});
const icons={
  15:'__IMG:ticket-15__',16:'__IMG:ticket-16__',17:'__IMG:ticket-17__',18:'__IMG:ticket-18__',
  19:'__IMG:ticket-19__',20:'__IMG:ticket-20__',57:'__IMG:ticket-57__',58:'__IMG:ticket-58__',
  59:'__IMG:ticket-59__',60:'__IMG:ticket-60__',61:'__IMG:ticket-61__',62:'__IMG:ticket-62__',
  83:'__IMG:ticket-83__',84:'__IMG:ticket-84__',85:'__IMG:ticket-85__',86:'__IMG:ticket-86__',
  87:'__IMG:ticket-87__',88:'__IMG:ticket-88__',89:'__IMG:ticket-89__',
};
function picture(src){
  const image=new Image();image.src=src;return image;
}
const arrows={forward:picture('__IMG:rule-right__'),backward:picture('__IMG:rule-left__')};
const proof=Object.fromEntries(Object.entries({
  17:'__IMG:hop-proof-17__',18:'__IMG:hop-proof-18__',19:'__IMG:hop-proof-19__',
  59:'__IMG:hop-proof-59__',60:'__IMG:hop-proof-60__',61:'__IMG:hop-proof-61__',
  84:'__IMG:hop-proof-84__',85:'__IMG:hop-proof-85__',86:'__IMG:hop-proof-86__',87:'__IMG:hop-proof-87__',
}).map(([n,src])=>[n,picture(src)]));
const hints=['顺着这关的箭头再数一格。','从刚才站稳的票号想，紧接着是哪张？'];
const cue={hint:'hop-hint',hint2:'hop-help',praise:'hop-praise'};
const options=K.gameTemplates.platformHop({
  art:{icons},voiceLead:true,
  cues:[{...cue,goal:'hop-forward'},{...cue,goal:'hop-wrap'},{...cue,goal:'hop-backward'}],
  levels:[
    {startLabel:16,mode:'forward',route:[17,18,19],speed:280,prompt:null,hints,
      platforms:[[71,490,129,'start'],[185,370,85,20],[257,474,111,17],[448,462,111,18],[544,358,86,15],[643,485,111,19]]},
    {startLabel:58,mode:'forward',route:[59,60,61],speed:288,prompt:null,hints,
      platforms:[[71,490,129,'start'],[185,367,85,57],[259,459,109,59],[451,484,108,60],[542,367,85,62],[651,465,106,61]]},
    {startLabel:88,mode:'backward',route:[87,86,85,84],speed:294,prompt:null,hints,
      platforms:[[1078,490,126,'start'],[921,464,99,87],[746,497,97,86],[698,369,74,89],
        [572,470,96,85],[394,500,94,84],[300,389,75,83]]},
  ],doneText:'从前往后、从后往前，都跳对了！',
});
function draw(context,img,x,y,w,h){
  if(img?.complete&&img.naturalWidth)context.drawImage(img,x,y,w,h);
}
options.drawTop=(game,context)=>{
  const {level,w}=game.data;
  if(!w)return;
  draw(context,arrows[level.mode],45,146,173,125);
  if(w.i)draw(context,proof[level.route[w.i-1]],992,288,247,139);
};
K.game(options);
K.$('[data-arc-input=action]').id='ticket-jump';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};

K.ready({title:'完整道具串放进装箱车',sub:'接住一整串。够一份装满袋，不够一份放余量盘。'});
const start = K.$('#ready .pic');
start.style.objectFit = 'contain';
start.addEventListener('error', () => { start.src = '__IMG:one-full-group__'; }, {once:true});

const hints = ['停一下，先数一整串有几个，再选篮。','完整一串比照左边的一份图；小串留给余量盘。'];
const cue = {goal:'catch-goal',hint:'catch-hint',hint2:'catch-help',praise:'catch-praise'};
const options = K.gameTemplates.orchardCatch({
  art:{backdrop:'__IMG:packing-room__',sticker:'__IMG:finish-sticker__',
    frames:['__IMG:pack-cart__'],icons:{fruit:'__IMG:token-badge__'}},
  voiceLead:true,
  levels:[
    {group:3,capacity:[6,2],batches:[[3,1],[3,2],[2,0]],seconds:2.7,catchRadius:134,hints},
    {group:4,capacity:[8,3],batches:[[4,0],[4,2],[3,1]],seconds:2.55,catchRadius:120,hints},
    {group:2,capacity:[6,1],batches:[[2,2],[2,0],[2,1],[1,2]],seconds:2.4,catchRadius:110,wind:40,hints}
  ],
  cues:[cue,cue,cue],
  doneText:'每一满份都一样多，零散件留在余量盘。'
});
function marker(ctx,x,y,r){
  ctx.fillStyle='#a3403d';K.draw.circle(ctx,x,y,r);
  ctx.fillStyle='#ffe5ab';K.draw.circle(ctx,x-r*.26,y-r*.26,r*.24);
}
function drawnBag(ctx,x,y){
  ctx.fillStyle='#e8b967';
  K.draw.rr(ctx,x,y,34,34,6);ctx.fill();
  ctx.fillStyle='#315e51';
  K.draw.rr(ctx,x+6,y+6,22,4,2);ctx.fill();
}
options.drawTop = (game, ctx) => {
  const {w,level}=game.data;
  if(!level||!w)return;
  ctx.fillStyle='#fff0cf';K.draw.rr(ctx,45,260,250,130,17);ctx.fill();
  K.draw.text(ctx,String(level.group),81,298,38,'#284c46');
  for(let i=0;i<level.group;i++)marker(ctx,119+i*35,300,12);
  const full=Math.floor(w.fill[0]/level.group);
  for(let i=0;i<full;i++)drawnBag(ctx,76+i*55,338);
};
options.onState = (_game,state) => {
  if(state.pause===false||state.demo===false){
    for(const anchor of K.$$('.teach-hl'))anchor.classList.remove('teach-hl');
  }
};
K.game(options);

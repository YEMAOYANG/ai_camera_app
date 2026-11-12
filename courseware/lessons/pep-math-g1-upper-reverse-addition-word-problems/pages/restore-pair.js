const problems = {
  'tile-3-8': {parts:[3,8],picture:'__IMG:workcard-3-8__'},
  'tile-4-9': {parts:[4,9],picture:'__IMG:workcard-4-9__'},
  'tile-6-9': {parts:[6,9],picture:'__IMG:workcard-6-9__'},
  'tile-8-6': {parts:[8,6],picture:'__IMG:workcard-8-6__'},
  'tile-5-7': {parts:[5,7],picture:'__IMG:workcard-5-7__'},
  'tile-9-8': {parts:[9,8],picture:'__IMG:workcard-9-8__'},
  'tile-8-8': {parts:[8,8],picture:'__IMG:workcard-8-8__'},
  'tile-6-7': {parts:[6,7],picture:'__IMG:workcard-6-7__'},
};
const sum = ([a,b]) => a+b;
const past = (n) => 'past-'+n;
const hints = ['先想要找动作之前，还是动作以后的数。','两部分合起来，再看同一排相邻的位置。'];
const levels = [
  {bottom:[null,past(11),null,past(13),null,null],pieces:['tile-3-8','tile-4-9'],interval:1.75},
  {bottom:[past(14),null,past(15),null,past(12),null],pieces:['tile-6-9','tile-8-6','tile-5-7'],interval:1.35},
  {bottom:['after-13',past(17),null,past(13),null,past(16)],pieces:['tile-9-8','tile-6-7','tile-8-8'],interval:.95},
];
const feedback = {hint:'tile-hint',hint2:'tile-help',praise:'tile-praise'};
const title = '拼出原来的托盘';
K.ready({title,sub:'看清两部分，把牌放在送走前总量的旁边。'});
const arcade = K.gameTemplates.fallingTiles({
  title,doneText:'两部分都算进去，找对了送走前的数量。',
  voiceLead:true,
  art:{
    backdrop:'__IMG:bench-backdrop__',sticker:'__IMG:nursery-sticker__',
    icons:{
      'tile-3-8':'__IMG:tile-3-8__','tile-4-9':'__IMG:tile-4-9__','tile-6-9':'__IMG:tile-6-9__',
      'tile-8-6':'__IMG:tile-8-6__','tile-5-7':'__IMG:tile-5-7__','tile-9-8':'__IMG:tile-9-8__',
      'tile-8-8':'__IMG:tile-8-8__','tile-6-7':'__IMG:tile-6-7__',
      'past-11':'__IMG:past-11__','past-12':'__IMG:past-12__','past-13':'__IMG:past-13__',
      'past-14':'__IMG:past-14__','past-15':'__IMG:past-15__','past-16':'__IMG:past-16__',
      'past-17':'__IMG:past-17__','after-13':'__IMG:after-13__',
    },
  },
  levels:levels.map(level=>({...level,hints,symbol:'↶',
    pairs:level.pieces.map(key=>[key,past(sum(problems[key].parts))])})),
  cues:levels.map((_,index)=>({...feedback,goal:index===2?'tile-goal-last':'tile-goal'})),
});
const proof = K.$('#tile-proof');
const picture = K.$('#tile-proof-picture');
const result = K.$('#tile-proof-result');
K.stage().appendChild(proof);
const draw = arcade.draw;
arcade.draw = (g,canvas) => {
  draw(g,canvas);
  const progress = g.data.progress;
  const pieces = g.data.level?.pieces;
  proof.hidden = !pieces || g.state==='ready' || g.state==='done';
  const completed = pieces ? pieces.slice(0,progress).map(key=>sum(problems[key].parts)).join(' · ') : '';
  if (g.state==='done' && completed) {
    const replay = K.$('#btn-again');
    if (replay && !K.$('.tile-finish-totals')) {
      const totals = K.el('div','tile-finish-totals');
      totals.textContent = completed;
      replay.parentElement.insertBefore(totals,replay);
    }
  }
  if (proof.hidden) return;
  const current = problems[pieces[Math.min(progress,pieces.length-1)]];
  if (picture.getAttribute('src')!==current.picture) {
    picture.src = current.picture;
    picture.alt = '送走'+current.parts[0]+'盆，剩下'+current.parts[1]+'盆';
  }
  if (result.textContent!==completed) result.textContent = completed;
};
K.game(arcade);

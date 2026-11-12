K.ready({title:'发射到合适的数量', sub:'听清参照、方向和远近，再瞄准发射。'});

const orders = {
  first:{picture:'__IMG:order-first__', clues:[[26,'more','far']]},
  'near-less':{picture:'__IMG:order-near-less__', clues:[[65,'less','near']]},
  'near-more':{picture:'__IMG:order-near-more__', clues:[[41,'more','near']]},
  'between-up':{picture:'__IMG:order-between-up__', clues:[[34,'more','far'],[90,'less','near']]},
  'between-down':{picture:'__IMG:order-between-down__', clues:[[57,'less','far'],[12,'more','near']]},
};
const quantities = {
  72:'__IMG:target-72__', 30:'__IMG:target-30__', 19:'__IMG:target-19__',
  61:'__IMG:target-61__', 21:'__IMG:target-21__', 45:'__IMG:target-45__', 83:'__IMG:target-83__',
  86:'__IMG:target-86__', 36:'__IMG:target-36__', 92:'__IMG:target-92__',
  15:'__IMG:target-15__', 56:'__IMG:target-56__', 9:'__IMG:target-9__',
};
const hints=['先找每条参照，检查在左边还是右边。','方向都对以后，再比较哪些候选明显近、哪些明显远。'];
const cues={hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'};

function level(queue, targets, speed, drift, targetWidth) {
  const accepted={};
  for (const key of queue) {
    const {clues}=orders[key];
    // Far and near describe this choice set. First keep the values on the
    // requested side of every reference, then compare their actual gaps.
    const candidates=targets.map(([value])=>value)
      .filter(value=>clues.every(([ref,side])=>side==='more'?value>ref:value<ref));
    if (candidates.length<2) throw new Error('comparison needs at least two directional candidates');
    const byDistance=candidates.filter(value=>clues.every(([ref,,span])=>{
      const gap=Math.abs(value-ref);
      return candidates.every(other=>value===other || (span==='near'?gap<Math.abs(other-ref):gap>Math.abs(other-ref)));
    }));
    if (byDistance.length!==1) throw new Error('comparison needs one clear target');
    accepted[key]=byDistance[0];
  }
  return {
    queue,targets:targets.map(([value,x])=>({value,x})),
    matches:(key,value)=>accepted[key]===value,
    hints,speed,drift,targetWidth,targetHeight:108,symbol:'seed',
  };
}
const game=K.game(K.gameTemplates.magnetMarbles({
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'每一条比较都检查过了，数量单收好了。',
  art:{
    backdrop:'__IMG:aim-backdrop__',
    frames:['__IMG:seed-marble__'],
    sticker:'__IMG:sprout-sticker__',
    icons:{...quantities,seed:'__IMG:sprout-sticker__',
      first:'__IMG:sprout-sticker__','near-less':'__IMG:sprout-sticker__','near-more':'__IMG:sprout-sticker__',
      'between-up':'__IMG:sprout-sticker__','between-down':'__IMG:sprout-sticker__'},
  },
  cues:[
    {...cues,goal:'aim-first',steps:['aim-first']},
    {...cues,goal:'aim-near-less',steps:['aim-near-less','aim-near-more']},
    {...cues,goal:'aim-between-up',steps:['aim-between-up','aim-between-down']},
  ],
  levels:[
    level(['first'],[[19,480],[30,640],[72,800]],452,0,146),
    level(['near-less','near-more'],[[21,460],[61,580],[83,700],[45,820]],468,3,108),
    level(['between-up','between-down'],[[92,319],[36,447],[15,575],[56,705],[86,833],[9,961]],484,4,116),
  ],
}));

function followGuide(id,box,source) {
  const image=K.$(id);
  game.follow(image, current=>{
    const {w,level}=current.data;
    const src=w && source(w,level);
    image.style.visibility=src?'visible':'hidden';
    if (!src) return null;
    if (image.getAttribute('src')!==src) image.setAttribute('src',src);
    return box;
  });
}
followGuide('#current-clue',{x:20,y:348,w:394,h:168},(w,level)=>orders[level.queue[Math.min(w.i,level.queue.length-1)]].picture);
followGuide('#chosen-quantity',{x:1000,y:363,w:220,h:142},w=>quantities[w.locked?.value]);

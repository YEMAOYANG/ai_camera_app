K.ready({title:'带展品走到展台',sub:'看右侧外框，找外形一样而且贴紧的拼图。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:one-complete-set__';},{once:true});

const icons={
  'r-tri':'__IMG:snake-r-tri__','t-small':'__IMG:snake-t-small__','t-big':'__IMG:snake-t-big__',
  't-three-q':'__IMG:snake-t-three-q__','t-three-p':'__IMG:snake-t-three-p__','t-four':'__IMG:snake-t-four__',
  'off-square':'__IMG:snake-off-square__','off-gap':'__IMG:snake-off-gap__','off-angled':'__IMG:snake-off-angled__',
  'r-rect':'__IMG:snake-r-rect__','rect-flat':'__IMG:snake-rect-flat__','rect-high':'__IMG:snake-rect-high__',
  'off-shift':'__IMG:snake-off-shift__',
};
const groups={'r-tri':'triangle','t-small':'triangle','t-big':'triangle','t-three-q':'triangle',
  't-three-p':'triangle','t-four':'triangle','r-rect':'rectangle','rect-flat':'rectangle','rect-high':'rectangle'};
const hints=['先绕外边看一圈。','看看外边的方向，也看看板有没有贴紧。'];
const cues={hint:'snake-hint',hint2:'snake-help',praise:'snake-praise'};
function level(start,seconds,foods){
  return {start,seconds,groups,hints,rounds:foods.map(row=>({relation:'match',foods:row}))};
}
K.game(K.gameTemplates.compareSnake({
  art:{backdrop:'__IMG:show-booth__',sticker:'__IMG:show-rosette__',icons},voiceLead:true,
  cues:[{...cues,goal:'snake-triangle'},{...cues,goal:'snake-variety'},{...cues,goal:'snake-rectangle'}],
  levels:[
    level('r-tri',.88,[[[5,3,'t-small'],[6,4,'off-square'],[2,2,'off-angled']],
      [[2,3,'t-big'],[6,3,'off-gap'],[4,1,'off-square']]]),
    level('r-tri',.76,[[[3,3,'t-three-q'],[5,3,'off-angled'],[8,2,'off-gap']],
      [[6,2,'t-four'],[4,2,'off-gap'],[2,2,'off-square']],[[5,2,'t-three-p'],[7,3,'off-gap'],[2,4,'off-angled']]]),
    level('r-rect',.67,[[[4,3,'rect-high'],[6,3,'off-square'],[3,1,'off-shift']],
      [[7,2,'rect-flat'],[5,3,'off-square'],[3,4,'off-shift']],[[2,1,'rect-high'],[6,2,'off-shift'],[7,4,'off-square']]]),
  ],doneText:'展品按外轮廓送到展台了！',
}));
K.$('[data-arc-input=up]').id='snake-forward';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};

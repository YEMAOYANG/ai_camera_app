const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = join(__dirname, '..');
const lesson = JSON.parse(readFileSync(join(root, 'lesson.json'), 'utf8'));
function config(page, template) {
  let value;
  const compass={};
  const K = {
    ready() {}, game(result) {value = result;}, $:()=>compass,
    stage:()=>({appendChild(node){assert.equal(node,compass);}}),
    gameTemplates:{[template]: options => options},
  };
  runInNewContext(readFileSync(join(root, 'pages', page + '.js'), 'utf8'), {K});
  return JSON.parse(JSON.stringify(value));
}

test('every narrated compass segment is straight and actually passable in the maze', () => {
  const game=config('follow-cardinal-route','bubbleMaze');
  const expected=[
    [[1,0],[0,-1],[1,0]],
    [[0,-1],[-1,0],[0,1]],
    [[-1,0],[0,1],[1,0]],
  ];
  for(const [index,level] of game.levels.entries()){
    const stops=['S',...level.route,'E'].map(token=>{
      const row=level.map.findIndex(r=>r.includes(token));
      return [level.map[row].indexOf(token),row];
    });
    const directions=[];
    for(let i=0;i<stops.length-1;i++){
      const [x,y]=stops[i], [endX,endY]=stops[i+1];
      const dx=Math.sign(endX-x),dy=Math.sign(endY-y);
      assert.equal(Math.abs(dx)+Math.abs(dy),1);
      for(let col=x+dx,row=y+dy;col!==endX||row!==endY;col+=dx,row+=dy){
        assert.equal(level.map[row][col],'.');
      }
      directions.push([dx,dy]);
    }
    assert.deepEqual(directions,expected[index]);
    assert.equal(game.cues[index].steps.length,3);
    assert.equal(level.listenOnly,true);
  }
});

test('three model times each declare both photos of exactly one time', () => {
  const game=config('direction-photo-pairs','shutterScout');
  const scene=lesson.scenes.find(s=>s.key==='direction-photo-pairs');
  const trial='one-model-two-views';
  assert.equal(game.observation.sceneId,'scene-direction-photo-pairs');
  for(const [i,phase] of ['morning','noon-model','evening'].entries()){
    const level=game.levels[i], rule=scene.observationCard.levels[i].trials[0];
    assert.equal(rule.id,trial);
    assert.deepEqual([...new Set(level.shots)].sort(),[0,1]);
    for(const view of ['top','side']){
      const id='shadow-'+view+'-'+phase;
      assert.equal(level.photoViews[view],id);
      assert.deepEqual(Object.keys(rule[view]),[id]);
      assert.equal(rule[view][id].image,id);
      assert.equal(game.observation.trials[trial][view][i],id);
      assert.ok(lesson.images[id]);
    }
  }
  assert.match(scene.observationCard.familyTask,/只观察地上影子/);
});

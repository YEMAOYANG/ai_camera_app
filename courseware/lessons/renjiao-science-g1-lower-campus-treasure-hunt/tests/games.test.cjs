const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const root=join(__dirname,'..');
const lesson=JSON.parse(readFileSync(join(root,'lesson.json'),'utf8'));
function config(page,template){
  let output;
  const compass={};
  const K={ready(){},game(v){output=v;},$:()=>compass,
    stage:()=>({appendChild(node){assert.equal(node,compass);}}),
    gameTemplates:{[template]:options=>options}};
  runInNewContext(readFileSync(join(root,'pages',page+'.js'),'utf8'),{K,Image:class Image{}});
  return JSON.parse(JSON.stringify(output));
}

test('oral route lengths and directions match all straight passable segments',()=>{
  const maze=config('draw-then-drive','bubbleMaze');
  const expected=[[[4,0],[0,-2],[2,0]],[[-4,0],[0,-4],[4,0]],[[5,0],[0,-3],[-4,0],[0,2]]];
  for(const [index,level] of maze.levels.entries()){
    const stops=['S',...level.route,'E'].map(token=>{
      const row=level.map.findIndex(r=>r.includes(token));
      return [level.map[row].indexOf(token),row];
    });
    const segments=[];
    for(let i=1;i<stops.length;i++){
      const [x,y]=stops[i-1],[endX,endY]=stops[i];
      const dx=endX-x,dy=endY-y;
      const step=[Math.sign(dx),Math.sign(dy)];
      assert.equal(Math.abs(step[0])+Math.abs(step[1]),1);
      for(let u=x+step[0],v=y+step[1];u!==endX||v!==endY;u+=step[0],v+=step[1]){
        assert.equal(level.map[v][u],'.');
      }
      segments.push([dx,dy]);
    }
    assert.deepEqual(segments,expected[index]);
    assert.equal(maze.cues[index].steps.length,level.route.length+1);
    assert.equal(level.listenOnly,true);
  }
});

test('each checkpoint allowlist accepts both views of its own doorway',()=>{
  const game=config('verify-the-door','shutterScout');
  const scene=lesson.scenes.find(s=>s.key==='verify-the-door');
  assert.equal(game.observation.sceneId,'scene-verify-the-door');
  for(const [i,room] of ['reading','music','studio'].entries()){
    const pair={top:'checkpoint-top-'+room,side:'checkpoint-front-'+room};
    const level=game.levels[i],card=scene.observationCard.levels[i].trials[0];
    assert.deepEqual(level.photoViews,pair);
    assert.deepEqual([...new Set(level.shots)].sort(),[0,1]);
    for(const [view,id] of Object.entries(pair)){
      assert.equal(game.observation.trials['one-door-two-views'][view][i],id);
      assert.deepEqual(Object.keys(card[view]),[id]);
      assert.equal(card[view][id].image,id);
      assert.ok(lesson.images[id]);
    }
  }
});

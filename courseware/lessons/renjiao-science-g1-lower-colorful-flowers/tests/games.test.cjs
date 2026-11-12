const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const root=join(__dirname,'..');
const lesson=JSON.parse(readFileSync(join(root,'lesson.json'),'utf8'));
function config(page,template){
  let result;
  const K={ready(){},game(v){result=v;},gameTemplates:{[template]:options=>options}};
  runInNewContext(readFileSync(join(root,'pages',page+'.js'),'utf8'),{K});
  return JSON.parse(JSON.stringify(result));
}

test('the sorter groups shapes and retains a real first wrong dock',()=>{
  const game=config('sort-flower-shapes','sortingDepot');
  const shape={'glory-side':'trumpet','pink-trumpet':'trumpet','cress-top':'cross',
    'yellow-cross':'cross','golden-bell':'bell','pea-flower':'butterfly'};
  for(const [i,level] of game.levels.entries()){
    assert.equal(level.items.length,i+2);
    for(const item of level.items){
      assert.equal(item.group,shape[item.token]);
      assert.equal(level.docks.find(d=>d.group===item.group).sample,'shape-'+item.group);
    }
  }
  assert.notEqual(game.levels[0].docks[1].group,game.levels[0].items[0].group);
});

test('the card allowlist binds only the actual flower pair for that level',()=>{
  const game=config('flower-photo-pairs','shutterScout');
  const scene=lesson.scenes.find(s=>s.key==='flower-photo-pairs');
  assert.equal(game.observation.sceneId,'scene-flower-photo-pairs');
  for(const [index,group] of ['trumpet','cross','peach'].entries()){
    const level=game.levels[index], trial=scene.observationCard.levels[index].trials[0];
    assert.deepEqual([...new Set(level.shots)].sort(),[0,1]);
    for(const view of ['top','side']){
      const id='flower-'+view+'-'+group;
      assert.equal(level.photoViews[view],id);
      assert.equal(game.observation.trials['same-flower-two-views'][view][index],id);
      assert.deepEqual(Object.keys(trial[view]),[id]);
      assert.equal(trial[view][id].image,id);
      assert.ok(lesson.images[id]);
    }
  }
});

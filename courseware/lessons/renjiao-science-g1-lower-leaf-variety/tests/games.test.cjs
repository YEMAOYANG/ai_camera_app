const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const root=join(__dirname,'..');
const lesson=JSON.parse(readFileSync(join(root,'lesson.json'),'utf8'));
function config(page,template){
  let value;
  const K={ready(){},game(v){value=v;},gameTemplates:{[template]:options=>options}};
  runInNewContext(readFileSync(join(root,'pages',page+'.js'),'utf8'),{K});
  return JSON.parse(JSON.stringify(value));
}

test('every leaf groups by its blade outline and every sample is a neutral silhouette',()=>{
  const game=config('sort-by-visible-leaf-shape','sortingDepot');
  const bySpecimen={'ginkgo-top':'fan','gold-ginkgo':'fan','maize-top':'long',
    'straw-maize':'long','lotus-blade':'round','pale-camphor':'broad'};
  for(const [index,level] of game.levels.entries()){
    assert.equal(level.items.length,index+2);
    for(const leaf of level.items){
      assert.equal(leaf.group,bySpecimen[leaf.token]);
      const samples=level.docks.filter(dock=>dock.group===leaf.group);
      assert.equal(samples.length,1);
      assert.equal(samples[0].sample,'dock-'+leaf.group);
    }
  }
  assert.notEqual(game.levels[0].items[0].group,game.levels[0].docks[1].group);
});

test('camera allowlists keep both orthogonal photos tied to each specimen',()=>{
  const game=config('paired-leaf-observations','shutterScout');
  const scene=lesson.scenes.find(s=>s.key==='paired-leaf-observations');
  assert.equal(game.observation.sceneId,'scene-paired-leaf-observations');
  for(const [i,specimen] of ['fan','long','broad'].entries()){
    const l=game.levels[i],rule=scene.observationCard.levels[i].trials[0];
    assert.deepEqual([...new Set(l.shots)].sort(),[0,1]);
    for(const view of ['top','side']){
      const id='view-'+view+'-'+specimen;
      assert.equal(l.photoViews[view],id);
      assert.equal(game.observation.trials['same-leaf-two-views'][view][i],id);
      assert.deepEqual(Object.keys(rule[view]),[id]);
      assert.equal(rule[view][id].image,id);
      assert.ok(lesson.images[id]);
    }
  }
});

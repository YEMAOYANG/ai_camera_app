const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = join(__dirname, '..');
const lesson = JSON.parse(readFileSync(join(root, 'lesson.json'), 'utf8'));

function configuration(page, template) {
  let result;
  const K = {ready(){}, $: () => ({}), game(value){result=value;}, gameTemplates:{[template]: options=>options}};
  runInNewContext(readFileSync(join(root, 'pages', page+'.js'), 'utf8'), {K});
  return JSON.parse(JSON.stringify(result));
}

test('only real captures of the specimen selected for that level can fill both views', () => {
  const game = configuration('campus-plant-photos', 'shutterScout');
  const card = lesson.scenes.find(scene=>scene.key==='campus-plant-photos').observationCard;
  const trialId = 'same-branch-two-views';
  assert.equal(game.observation.sceneId, 'scene-campus-plant-photos');
  for(const [index,specimen] of ['jasmine','forsythia','willow'].entries()) {
    const level = game.levels[index], trial = card.levels[index].trials[0];
    assert.equal(trial.id, trialId);
    assert.deepEqual([...new Set(level.shots)].sort(), [0,1]);
    for(const view of ['top','side']) {
      const asset = 'plant-'+view+'-'+specimen;
      assert.equal(level.photoViews[view], asset);
      assert.equal(game.observation.trials[trialId][view][index], asset);
      assert.deepEqual(Object.keys(trial[view]), [asset]);
      assert.equal(trial[view][asset].image, asset);
      assert.ok(lesson.images[asset]);
    }
  }
});

test('camera feedback stays above the target image and the camera controls', () => {
  let camera;
  const K = {gameTemplates:{}, ready() {}, game(value) { camera = value; }};
  const Classic = {
    create: (_config, logic) => logic,
    center: (x,y,w,h) => ({x:x-w/2,y:y-h/2,w,h}),
  };
  const context = {K, Classic};
  const kit = join(root, '..', '..', 'kit', 'game_templates');
  for (const file of [join(kit, 'shutterScout.js'), join(root, 'pages', 'campus-plant-photos.js')])
    runInNewContext(readFileSync(file, 'utf8'), context);

  const {x,y} = camera.bubbleAt();
  const target = camera.goalAnchor();
  assert.equal(x, target.x + target.w / 2);
  assert.ok(y - 34 - 2 >= 0); // The rectangle includes half of its four-pixel stroke.
  assert.ok(y + 52 < target.y); // The tail is filled without a stroke.
  assert.ok(y + 52 < 609);
});

test('matching maps each local clue to the exact whole plant, even for two yellow flowers', () => {
  const game = configuration('match-plant-evidence', 'magnetMarbles');
  const correct = {'clue-jasmine':'whole-jasmine','clue-forsythia':'whole-forsythia',
    'clue-willow':'whole-willow','clue-pine':'whole-pine'};
  assert.deepEqual(game.levels.map(level=>level.queue.length), [2,3,4]);
  for(const level of game.levels) {
    assert.deepEqual(level.pairs, level.queue.map(clue=>[clue,correct[clue]]));
    for(const [clue,target] of level.pairs) {
      assert.equal(level.targets.filter(t=>t.value===target).length, 1);
      assert.ok(lesson.images[clue]);
      assert.ok(lesson.images[target]);
    }
  }
  assert.equal(game.levels[0].targets.find(t=>t.x===640).value, 'whole-forsythia');
  assert.equal(game.levels[0].queue[0], 'clue-jasmine');
});

test('the teacher launch highlight resolves to the shared template button itself', () => {
  const scene = lesson.scenes.find(item => item.key === 'match-plant-evidence');
  const launch = scene.script.find(beat => beat.highlight === '#plant-launch').highlight;
  const markup = readFileSync(join(root, 'pages', scene.page + '.html'), 'utf8');
  assert.doesNotMatch(markup, /id="plant-launch"/);

  const nodes = [];
  function node(tag) {
    const item = {
      tag, attrs: {}, dataset: {}, classList: {add() {}}, addEventListener() {},
      setAttribute(name, value) { this.attrs[name] = value; },
    };
    nodes.push(item);
    return item;
  }
  const stage = node('div');
  const K = {
    gameTemplates: {}, sfx: {}, ready() {}, stage: () => stage, el: node,
    $(selector) {
      if (selector.startsWith('#')) return nodes.find(item => item.id === selector.slice(1));
      const control = /^button\[data-arc-input="([^"]+)"\]$/.exec(selector);
      assert.ok(control, selector);
      return nodes.find(item => item.tag === 'button' && item.attrs['data-arc-input'] === control[1]);
    },
    game(opts) { opts.setup({follow() {}}); },
  };
  const events = {addEventListener() {}};
  const context = {K, Image: class {}, W: events, D: events, gameCueLead: () => ({})};
  const kit = join(root, '..', '..', 'kit', 'game_templates');
  for (const file of [join(kit, 'classic.js'), join(kit, 'magnetMarbles.js'), join(root, 'pages', scene.page + '.js')])
    runInNewContext(readFileSync(file, 'utf8'), context);

  const button = K.$('button[data-arc-input="action"]');
  assert.equal(button.attrs['aria-label'], '发射弹珠');
  assert.equal(K.$(launch), button);
  assert.equal(nodes.filter(item => item.id === 'plant-launch').length, 1);
});

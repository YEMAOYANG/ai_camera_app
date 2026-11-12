const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const templates = path.resolve(__dirname, '../../../kit/game_templates');
const lesson = path.resolve(__dirname, '..');
const read = name => JSON.parse(readFileSync(path.join(lesson, name), 'utf8'));
const assets = read('asset-sources.json').assets;
const content = read('lesson.json');
const readJs = file => readFileSync(file, 'utf8');
const noop = () => {};
const input = (...keys) => ({ press: key => keys.includes(key), held: key => keys.includes(key) });

function loadGame(template, page) {
  const elements = new Map();
  const context = vm.createContext({
    K: {
      $(selector) {
        if (!elements.has(selector)) elements.set(selector, { dataset: {} });
        return elements.get(selector);
      },
      stage: () => ({ append: noop }), ready: noop,
      game(game) { context.loaded.game = game; return { follow: noop }; },
    },
  });
  vm.runInContext(readJs(path.join(templates, 'classic.js')), context);
  vm.runInContext(`
    Classic.create = (config, mechanic) => {
      globalThis.loaded = {config, mechanic};
      config.levels.forEach(mechanic.validate);
      return {draw(){}};
    };
  `, context);
  vm.runInContext(readJs(path.join(templates, template + '.js')), context);
  vm.runInContext(readJs(path.join(lesson, 'pages', page + '.js')), context);
  return { ...context.loaded, elements };
}

function player(mechanic, level) {
  const world = mechanic.reset(level);
  let score = 0;
  let misses = 0;
  const feedback = {
    fx: noop, move: noop, jump: noop, drop: noop,
    resetCheckpoint() { score = 0; },
    award() { score++; },
    lost() { misses++; mechanic.adapt(world, misses); },
  };
  const dt = 1 / 60;
  return {
    world, get score() { return score; }, get misses() { return misses; },
    update(keys = input()) { mechanic.update(world, level, keys, dt, feedback); },
    finish() {
      for (let frame = 0; frame < 5400 && score < mechanic.goal(level); frame++) {
        mechanic.update(world, level, mechanic.pilot(world, level, dt), dt, feedback);
      }
      assert.equal(score, mechanic.goal(level));
    },
  };
}

const unitNames = {y:'yuan',j:'jiao',f:'fen'};

test('all three depot layouts route by printed unit rather than face number', () => {
  const { config, mechanic } = loadGame('sortingDepot', 'sort-the-change');
  for (const level of config.levels) {
    for (const {token,group} of level.items) assert.equal(unitNames[assets['sort-' + token].semantics.unit], group);
    for (const {sample,group} of level.docks) assert.equal(unitNames[assets['sort-' + sample].semantics.unit], group);
    for (let round = 0; round < 2; round++) player(mechanic, level).finish();
  }
  const trial = player(mechanic, config.levels[0]);
  for (const key of ['up','right','down']) {
    trial.update(input(key));
    for (let tick = 0; tick < 24; tick++) trial.update();
  }
  assert.equal(trial.misses, 1);
  assert.equal(trial.score, 0);
  trial.finish();
});

test('all marble orders need both equal value and requested unit; wrong shot recovers', () => {
  const { config, mechanic, game, elements } = loadGame('magnetMarbles', 'aim-for-the-same-value');
  const orders = [['yuan','yuan'],['jiao','fen'],['yuan','jiao']];
  for (const [levelIndex,level] of config.levels.entries()) {
    assert.equal(level.matches(undefined,undefined),false);
    for (const [orderIndex,id] of level.queue.entries()) {
      const order = assets[id].semantics;
      const candidates = level.targets.filter(t => level.matches(id,t.value));
      assert.equal(candidates.length,1);
      const target=assets[candidates[0].value].semantics;
      assert.equal(target.valueFen,order.valueFen);
      assert.ok(target.groups.flat().every(token=>unitNames[token[1]]===orders[levelIndex][orderIndex]));
    }
    for (let round = 0; round < 2; round++) player(mechanic,level).finish();
  }
  const level=config.levels[1];
  const trial=player(mechanic,level);
  trial.update(input('action'));
  for(let frame=0;frame<90;frame++)trial.update();
  assert.equal(trial.score,0);
  assert.equal(trial.misses,1);
  trial.finish();
  assert.doesNotThrow(()=>mechanic.target(trial.world,level));
  game.draw({state:'between',data:{level,w:trial.world}});
  assert.equal(elements.get('#exchange-order').hidden,true);
});

test('six quiz choices independently resolve from exact denomination art', () => {
  const questions=content.scenes.filter(s=>s.type==='quiz').flatMap(s=>s.questions);
  const predicates=[
    spec=>spec.groups.flat()[0][1]==='y',
    spec=>spec.unitTotals.y===11&&spec.unitTotals.j===6,
    spec=>spec.unitTotals.j===5&&spec.unitTotals.f===3,
    spec=>spec.valueFen===5000,
    spec=>spec.valueFen===200&&spec.unitTotals.j===20,
    spec=>spec.valueFen===20&&spec.unitTotals.f===20,
  ];
  assert.equal(questions.length,predicates.length);
  questions.forEach((q,index)=>{
    const valid=Object.entries(q.options).filter(([,o])=>predicates[index](assets[o.visual.image].semantics)).map(([k])=>k);
    assert.deepEqual(valid,q.answer);
  });
});

test('teaching comparisons have the counted totals and one-to-ten groups', () => {
  assert.deepEqual(assets['same-one-yuan'].semantics.groupFen,[100,100]);
  assert.deepEqual(assets['yuan-jiao-boxes'].semantics.groupFen,[2500,20]);
  assert.deepEqual(assets['left-fifteen'].semantics.groupFen,assets['right-fifteen'].semantics.groupFen);
  assert.deepEqual(assets['ten-jiao'].semantics.groups[0],Array(10).fill('cj1'));
  assert.deepEqual(assets['ten-fen'].semantics.groups[1],Array(10).fill('cf1'));
  assert.deepEqual(assets['ten-fen'].semantics.groupFen,[10,10]);
  assert.deepEqual(assets['five-and-five-fen'].semantics.groupFen,[10]);
});

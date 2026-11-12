import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = name => readFileSync(new URL(name, import.meta.url), 'utf8');
const dt = 1 / 60;

function loadGame(page, template) {
  let game;
  const K = {
    ready() {},
    $: () => ({ style: {}, addEventListener() {} }),
    game: value => { game = value; },
  };
  const scope = vm.createContext({ K, capture: (config, rules) => ({ config, rules }) });
  vm.runInContext(read('../../../kit/game_templates/classic.js') + '\nClassic.create = capture;', scope);
  vm.runInContext(read('../../../kit/game_templates/' + template + '.js'), scope);
  vm.runInContext(read('../pages/' + page + '.js'), scope);
  return game;
}

function advance({ rules }, level, world, keys, feedback, frames) {
  for (let frame = 0; frame < frames; frame++) {
    const key = keys(frame);
    rules.update(world, level, key, dt, feedback);
  }
}

function feedback() {
  const result = { awards: [], misses: [], move() {}, drop() {}, fx() {}, resetCheckpoint() {} };
  result.award = (x,y) => result.awards.push([x,y]);
  result.lost = (x,y) => result.misses.push([x,y]);
  return result;
}

function pilot(game, level, index) {
  const {rules} = game;
  rules.validate(level,index);
  const world = rules.reset(level);
  const result = feedback();
  for (let frame = 0; frame < 7200 && result.awards.length < rules.goal(level); frame++) {
    rules.update(world,level,rules.pilot(world,level,dt),dt,result);
  }
  assert.equal(result.awards.length,rules.goal(level));
  assert.deepEqual(result.misses,[]);
  return { world, result };
}

const tap = key => frame => ({ held: () => false, press: query => frame === 0 && key === query });

test('字卡只有到相合的结构盘才得分，三关均可按实际推动规则完成', () => {
  const game = loadGame('move-character-crates','sortingDepot');
  const {config,rules} = game;
  const group = { only:'up',ox:'whole',sheep:'whole',dawn:'up',assemble:'side',
    bell:'up',white:'whole',fruit:'whole',leaf:'side' };
  assert.deepEqual(Array.from(config.levels,level=>level.items.length),[2,3,4]);
  for (const [index,level] of config.levels.entries()) {
    for (const item of level.items) assert.equal(item.group,group[item.token]);
    for (const dock of level.docks) assert.equal(dock.sample,dock.group);
    const { world,result } = pilot(game,level,index);
    assert.ok(world.state.items.every(position => position < 0));
    if (index === 0) assert.deepEqual(result.awards[0],[757,303]);
  }
  const first = config.levels[0];
  const wrong = rules.reset(first);
  const result = feedback();
  for (const key of ['down','down','right','right','right','up']) {
    advance(game,first,wrong,tap(key),result,32);
  }
  assert.equal(result.awards.length,0);
  assert.equal(result.misses.length,1);
  assert.equal(wrong.help,false);
});

test('小艇根据每条录音接住有语义的目标图，首错后无标亮', () => {
  const game = loadGame('listen-to-scenes','wordBubbles');
  const {config,rules} = game;
  const expected = [['fruit','bark'],['returning','answering','many'],['leaves','waves','bamboo','flowers']];
  assert.equal(config.voiceLead,true);
  assert.equal(config.stepVoiceLead,true);
  for (const [index,level] of config.levels.entries()) {
    assert.deepEqual(Array.from(level.rounds,round=>round.target),expected[index]);
    assert.equal(level.rounds.length,config.cues[index].steps.length);
    for (const round of level.rounds) {
      for (const key of round.cards) assert.match(config.art.icons[key],/^__IMG:/);
    }
    const {world} = pilot(game,level,index);
    assert.equal(world.caught.token,expected[index].at(-1));
  }
  const first = config.levels[0];
  const world = rules.reset(first);
  const result = feedback();
  advance(game,first,world,tap('action'),result,40);
  assert.deepEqual([result.awards.length,result.misses.length,world.help],[0,1,false]);
});

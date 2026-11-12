import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const lesson = JSON.parse(read('../lesson.json'));
const dt = 1 / 60;
const noop = () => {};

function load(page, template) {
  let game;
  const removed = [];
  const K = {
    ready:noop,
    $:() => ({addEventListener:noop}),
    $$:() => [{classList:{remove:name => removed.push(name)}}],
    game:value => { game = value; }
  };
  const scope = vm.createContext({K, Image:class {}, capture:(config,rules) => ({config,rules})});
  vm.runInContext(read('../../../kit/game_templates/classic.js')+'\nClassic.create=capture;',scope);
  vm.runInContext(read('../../../kit/game_templates/'+template+'.js'),scope);
  vm.runInContext(read('../pages/'+page+'.js'),scope);
  return {...game,removed};
}

function driver({rules}, level) {
  const world = rules.reset(level);
  const events = [];
  const feedback = {
    award:(x,y) => events.push({type:'award',x,y}),
    lost:(x,y) => events.push({type:'lost',x,y}),
    fx:noop, move:noop, jump:noop, drop:noop, resetCheckpoint:noop
  };
  const update = input => rules.update(world,level,input,dt,feedback);
  function play(pickInput, stop) {
    for (let frame=0; frame<7200 && !stop(); frame++) update(pickInput());
    assert.ok(stop(),'goal never reached');
  }
  const awards = () => events.filter(event => event.type==='award').length;
  return {world,events,awards,update,play};
}

function tapSequence(update, keys, waitFrames=28) {
  for (const key of keys) {
    for (let frame=0; frame<waitFrames; frame++) {
      update({press:query => frame===0 && query===key, held:() => false});
    }
  }
}

function verifyPilots(game, expectedAwards) {
  const {config,rules} = game;
  for (const [index,level] of config.levels.entries()) {
    rules.validate(level,index);
    assert.equal(rules.goal(level),expectedAwards[index]);
    for (let repeat=0; repeat<2; repeat++) {
      const {world,events,awards,play} = driver(game,level);
      play(() => rules.pilot(world,level,dt),() => awards()===expectedAwards[index]);
      assert.equal(events[0].type,'award','teacher first move must not score a miss');
      assert.ok(events.every(event => event.type==='award'),'autopilot route must avoid false hints');
    }
  }
}

test('delivery rewards correct pickups and recipients, with a clean first demonstration', () => {
  const game = load('listen-props','listenDelivery');
  verifyPilots(game,[2,2,4]);
  const level = game.config.levels[0];
  const {world,events,update} = driver(game,level);
  tapSequence(update,['left','left','action']);
  assert.equal(world.col,2);
  assert.equal(world.help,false);
  assert.deepEqual(events.map(event => event.type),['lost']);
  assert.equal(world.carried,null);
  assert.equal(world.order,0);
  const shown = driver(game,level);
  shown.play(() => game.rules.pilot(shown.world,level,dt),() => shown.awards()===1);
  assert.equal(shown.world.carried,'baby-noodles');
  assert.equal(shown.world.order,0);
});

test('story route only accepts the current event and never uses a locked exit to reach it', () => {
  const game = load('story-order','bubbleMaze');
  verifyPilots(game,[3,4,5]);
  const level = game.config.levels[0];
  const shown = driver(game,level);
  shown.play(() => game.rules.pilot(shown.world,level,dt),() => shown.awards()===1);
  assert.deepEqual([shown.world.x,shown.world.y,shown.world.i],[3,4,1]);
  const wrong = driver(game,level);
  tapSequence(wrong.update,['right','right','right','right','up','right','right','down']);
  assert.deepEqual([wrong.world.x,wrong.world.y],[7,5]);
  assert.equal(wrong.world.help,false);
  assert.deepEqual(wrong.events.map(event=>event.type),['lost']);
  assert.equal(wrong.world.i,0);
});

test('both natural introductions speak before the demo and clear old visuals on motion and handoff', () => {
  for (const [key,template] of [['listen-props','listenDelivery'],['story-order','bubbleMaze']]) {
    const page=lesson.scenes.find(scene => scene.key===key);
    assert.ok(page.script[0].say);
    assert.deepEqual(page.script[1].setState,{demo:true,level:1,pause:true});
    assert.deepEqual(page.script.at(-1).setState,{demo:false,level:1,pause:false});
    const game=load(key,template);
    game.onState(null,{demo:true,pause:true});
    assert.deepEqual(game.removed,[]);
    game.onState(null,{pause:false});
    game.onState(null,{demo:false,level:1,pause:false});
    assert.deepEqual(game.removed,['teach-hl','teach-hl']);
    const html=read('../pages/'+key+'.html');
    for (const beat of page.script.filter(beat => beat.highlight)) {
      assert.ok(html.includes('id="'+beat.highlight.slice(1)+'"'));
    }
    for (const group of game.config.cues) {
      for (const id of [group.goal,group.hint,group.hint2,group.praise,...group.steps]) {
        const ref=page.gameAudio[id];
        const dash=ref.lastIndexOf('-');
        const scene=lesson.scenes.find(scene => scene.key===ref.slice(0,dash));
        assert.ok(scene.script[Number(ref.slice(dash+1))-1].say);
      }
    }
  }
});

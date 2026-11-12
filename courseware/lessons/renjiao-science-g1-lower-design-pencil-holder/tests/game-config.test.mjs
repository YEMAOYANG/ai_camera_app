import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const root = new URL('../../../../', import.meta.url);
const lesson = new URL('../', import.meta.url);
const text = (name, base) => readFileSync(new URL(name, base), 'utf8');

function mechanic(template, page) {
  let capture;
  const context = vm.createContext({
    K: {ready() {}, gameTemplates: {}, $: () => ({}),
        game: game => { capture = game; return {follow() {}}; }},
  });
  vm.runInContext(text('courseware/kit/game_templates/classic.js', root) +
    '\nClassic.create=(config,spec)=>({config,spec});', context);
  vm.runInContext(text('courseware/kit/game_templates/'+template+'.js', root), context);
  vm.runInContext(text('pages/'+page+'.js', lesson), context);
  assert(capture);
  return capture;
}

function autoplay(spec, world, level, feedback, complete, images) {
  for (let i = 0; i < 9000 && !complete(); i++) {
    const dt = 1 / 60;
    spec.update(world, level, spec.pilot(world, level, dt), dt, feedback, images);
  }
  assert(complete(), 'The approved pilot could not complete the actual lesson layout');
}

function feedback(award, lost, observe = () => {}) {
  return {fx() {}, move() {}, jump() {}, drop() {}, award, lost, observe,
          resetCheckpoint() {}};
}

test('each part fits a purpose and all three existing layouts solve', () => {
  const {config, spec} = mechanic('sortingDepot', 'sort-parts');
  assert.equal(config.levels.length, 3);
  for (const level of config.levels) {
    assert.deepEqual(Array.from(level.items, item => item.group).sort(),
      Array.from(level.docks, dock => dock.group).sort());
    assert(level.docks.every(dock => dock.sample === 'use-'+dock.group));
    spec.validate(level, config.levels.indexOf(level));
    const state = spec.reset(level);
    let accepted = 0;
    autoplay(spec, state, level, feedback(() => accepted++, () => assert.fail('Unexpected miss')),
      () => accepted === level.items.length);
    assert(state.state.items.every(position => position < 0));
  }
});

test('the camera records only a completed actual pair, never a wrong angle', () => {
  const {config, spec} = mechanic('shutterScout', 'take-two-views');
  const images = {icons:new Map(Object.keys(config.art.icons).map(id => [id, {complete:true,naturalWidth:720}]))};
  for (const [index, level] of config.levels.entries()) {
    spec.validate(level, index);
    const state = spec.reset(level);
    let accepted = 0;
    let missed = 0;
    const records = [];
    const counters = feedback(() => accepted++, () => missed++,
      (trialId, views) => records.push({trialId, ...views}));
    if (index === 0) {
      state.t = .95;
      spec.update(state, level, {held:() => false, press:key => key === 'action'}, 1/60, counters, images);
      assert.equal(missed, 1);
      assert.equal(accepted, 0);
      assert.equal(records.length, 0);
    }
    autoplay(spec, state, level, counters, () => accepted === 1, images);
    assert.equal(records.length, 0, 'One picture is not a pair');
    autoplay(spec, state, level, counters, () => accepted === 2, images);
    assert.deepEqual(records, [{trialId:'same-load-views',
      top:'trial-'+(index+1)+'-top', side:'trial-'+(index+1)+'-side'}]);
  }
});

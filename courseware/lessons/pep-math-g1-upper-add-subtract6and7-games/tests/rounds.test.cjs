const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');

function lessonRounds(page, mechanic) {
  let config;
  vm.runInNewContext(readFileSync(join(__dirname, '..', 'pages', page + '.js'), 'utf8'), {
    K: {
      ready() {},
      game(value) { config = value; },
      gameTemplates: { [mechanic]: value => value }
    }
  });
  assert.equal(config.levels.length, 2);
  const [first, second] = config.levels;
  assert.ok(second.rounds.length > first.rounds.length);
  return [...first.demoRounds, ...first.rounds, ...second.rounds];
}

test('the runner can only fill each target by collecting the intended two groups', () => {
  for (const round of lessonRounds('collect', 'runner')) {
    const totals = [0];
    const solutions = [];
    for (const group of round.track) {
      for (const previous of totals.slice()) totals.push(previous + group.value);
    }
    assert.equal(totals.filter(n => n === round.collect).length, 1);
    for (const [i, a] of round.track.entries()) {
      for (const b of round.track.slice(i + 1)) {
        if (a.value + b.value === round.collect) solutions.push([a.value, b.value]);
      }
    }
    assert.equal(solutions.length, 1);
    assert.equal(round.goal.count, round.collect);
  }
});

test('every slingshot round takes precisely the goal group out of six or seven lamps', () => {
  for (const round of lessonRounds('aim', 'slingshot')) {
    const total = round.lamps.length;
    const matches = Array.from(round.matches);
    assert.ok(total === 6 || total === 7);
    assert.equal(round.goal.count, matches.length);
    assert.ok(total > matches.length);
    round.lamps.forEach((lamp, i) => assert.equal(matches.includes(i), lamp.color === round.goal.color));
  }
});

test('fishing accepts exactly the different equations for the pictured whole and parts', () => {
  for (const round of lessonRounds('fish', 'fishing')) {
    const [a, b] = round.goal.fallback.groups.map(group => group.count);
    const total = a + b;
    assert.ok(total === 6 || total === 7);
    const accepted = new Set([a + ' + ' + b + ' = ' + total, b + ' + ' + a + ' = ' + total,
      total + ' − ' + a + ' = ' + b, total + ' − ' + b + ' = ' + a]);
    assert.equal(accepted.size, round.matches.length);
    round.options.forEach((option, i) => assert.equal(round.matches.includes(i), accepted.has(option)));
  }
});

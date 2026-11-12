const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lessonDir = path.join(__dirname, '..');
const lesson = JSON.parse(fs.readFileSync(path.join(lessonDir, 'lesson.json'), 'utf8'));
const notes = JSON.parse(fs.readFileSync(path.join(lessonDir, 'official-notes.json'), 'utf8'));

function configFor(page, template) {
  const source = fs.readFileSync(path.join(lessonDir, 'pages', page + '.js'), 'utf8');
  let config;
  vm.runInNewContext(source, {
    K: {
      ready() {},
      game(value) { config = value; },
      gameTemplates: { [template]: (value) => value }
    }
  });
  return config;
}

test('every pictured stationery task has one fitting item and independent practice', () => {
  const { levels } = configFor('tool-rescue', 'parachute');
  const solution = {
    '__IMG:task-line__': '__IMG:ruler__',
    '__IMG:task-erase__': '__IMG:eraser__',
    '__IMG:task-pens__': '__IMG:pencilcase__'
  };
  assert.equal(levels.map((level) => level.rounds.length).join(), '1,2,3');
  assert.notEqual(levels[0].rounds[0].goal.image, levels[0].demoRounds[0].goal.image);
  for (const level of levels) {
    for (const round of [...level.rounds, ...(level.demoRounds || [])]) {
      const correct = round.options[round.answer];
      assert.equal(correct.image, solution[round.goal.image]);
      assert.equal(round.options.filter((option) => option.image === correct.image).length, 1);
      assert.ok(!round.hint.includes(correct.fallback));
      for (const visual of [round.goal, ...round.options]) {
        const key = /^__IMG:([\w-]+)__$/.exec(visual.image)?.[1];
        assert.ok(key && lesson.images[key]);
        assert.ok(fs.existsSync(path.join(lessonDir, lesson.images[key].file)));
      }
    }
  }
});

test('lecture-grid strokes use the same coordinates as the child’s driving route', () => {
  const { levels } = configFor('stroke-drive', 'trace');
  const routes = new Map(levels.flatMap((level) => level.rounds)
    .map((round) => [round.goal, round]));
  const diagramNames = ['dao-grid', 'chi-grid', 'writing-grid-set'];
  const found = new Set();
  for (const name of diagramNames) {
    const svg = fs.readFileSync(path.join(lessonDir, 'diagrams', name + '.svg'), 'utf8');
    for (const [, target, group] of svg.matchAll(/data-lesson-character="(.)">([\s\S]*?)<\/g>/gu)) {
      const round = routes.get(target);
      assert.ok(round);
      assert.ok(!found.has(target));
      found.add(target);
      const [cx, cy, size] = round.gridBox;
      const [left, top] = /<rect x="(\d+)" y="(\d+)"/.exec(group).slice(1).map(Number);
      const drawn = Array.from(group.matchAll(/<polyline points="([^"]+)"/g), (m) => m[1]);
      const expected = Array.from(round.strokes, (stroke) => stroke
        .map(([x, y]) => [x - cx + left + size / 2, y - cy + top + size / 2].join(','))
        .join(' '));
      assert.deepEqual(drawn, expected);
    }
  }
  assert.deepEqual([...found].sort(), [...routes.keys()].sort());
});

test('writing route covers all five textbook characters and preserves key stroke geometry', () => {
  const { levels } = configFor('stroke-drive', 'trace');
  const rounds = levels.flatMap((level) => level.rounds);
  assert.equal(rounds.map((round) => round.goal).join(''), '刀尺不本少');
  for (const round of rounds) {
    assert.equal(round.strokes.length, notes.characters.strokeOrder[round.goal].length);
    const [cx, cy, size] = round.gridBox;
    for (const stroke of round.strokes) {
      for (const [x, y] of stroke) {
        assert.ok(Math.abs(x - cx) < size / 2 && Math.abs(y - cy) < size / 2);
      }
    }
  }
  const [dao, chi, bu, ben, shao] = rounds;
  const daoHook = dao.strokes[0];
  assert.ok(daoHook[1][0] > daoHook[0][0] && daoHook[2][1] > daoHook[1][1]);
  assert.ok(daoHook.at(-1)[0] < daoHook.at(-2)[0] && daoHook.at(-1)[1] < daoHook.at(-2)[1]);
  assert.ok(chi.strokes[3].at(-1)[0] > chi.strokes[3][0][0]);
  assert.ok(bu.strokes[3].at(-1)[0] > bu.strokes[3][0][0]);
  assert.ok(ben.strokes[4][1][0] - ben.strokes[4][0][0] < ben.strokes[0][1][0] - ben.strokes[0][0][0]);
  assert.ok(shao.strokes[0].length === 2 && Math.abs(shao.strokes[0][1][0] - shao.strokes[0][0][0]) <= 2);
  assert.ok(shao.strokes[3].at(-1)[0] < shao.strokes[3][0][0]);
});

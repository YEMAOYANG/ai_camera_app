const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = path.join(__dirname, '..');
const lesson = JSON.parse(fs.readFileSync(path.join(source, 'lesson.json'), 'utf8'));

function configFor(page, template) {
  const script = fs.readFileSync(path.join(source, 'pages', page + '.js'), 'utf8');
  let config;
  vm.runInNewContext(script, {
    K: {
      ready() {},
      game(value) { config = value; },
      gameTemplates: { [template]: (value) => value }
    }
  });
  return config;
}

test('the crane serves each character containing the cargo component', () => {
  const { levels } = configFor('component-crane', 'crane');
  const parts = {
    明: ['日', '月'], 男: ['田', '力'], 尖: ['小', '大'], 尘: ['小', '土'],
    双: ['又'], 众: ['人'], 从: ['人'], 林: ['木'], 森: ['木']
  };
  assert.notEqual(levels[0].rounds[0].cargo, levels[0].demoRounds[0].cargo);
  assert.equal(levels.at(-1).rounds.every((r) => r.drop.length === 2), true);
  for (const level of levels) {
    for (const r of [...level.rounds, ...(level.demoRounds || [])]) {
      const expected = Array.from(r.cars).flatMap((char, index) =>
        parts[char].includes(r.cargo) ? [index] : []);
      assert.deepEqual(Array.from(r.drop), expected);
    }
  }
});

test('each fishing clue uses the registered image and has one meaning match', () => {
  const { levels } = configFor('shape-fishing', 'fishing');
  const answers = {'tilted-frame': '歪', tears: '泪', 'seedling-bed': '苗'};
  const first = levels[0];
  assert.notEqual(first.rounds[0].goal.image, first.demoRounds[0].goal.image);
  assert.equal(levels.map((l) => l.rounds[0].options.length).join(), '2,3,4');
  for (const l of levels) {
    for (const r of [...l.rounds, ...(l.demoRounds || [])]) {
      const asset = /^__IMG:([\w-]+)__$/.exec(r.goal.image)[1];
      assert.ok(fs.existsSync(path.join(source, lesson.images[asset].file)));
      assert.equal(r.matches.length, 1);
      assert.equal(r.options[r.matches[0]], answers[asset]);
      assert.ok(!r.hint.includes(answers[asset]));
    }
  }
});

test('the five grid images and the quiz derive from the playable stroke order', () => {
  const { levels } = configFor('stroke-drive', 'trace');
  const rounds = levels.flatMap((l) => l.rounds);
  assert.equal(rounds.map((r) => r.goal).join(''), '力男土木心');
  assert.equal(rounds.map((r) => r.strokes.length).join(), '2,7,3,4,4');
  const ids = ['force-grid', 'man-grid', 'soil-grid', 'wood-grid', 'heart-grid',
    'heart-left-dot', 'heart-middle-dot', 'heart-hook'];
  const highlighted = {'heart-left-dot': 0, 'heart-middle-dot': 2, 'heart-hook': 1};
  for (const id of ids) {
    const svg = fs.readFileSync(path.join(source, 'diagrams', id + '.svg'), 'utf8');
    const char = /data-lesson-character="(.)"/u.exec(svg)[1];
    const r = rounds.find((round) => round.goal === char);
    const [cx, cy] = r.gridBox;
    const lines = [...svg.matchAll(/polyline points="([^"]+)" fill="none" stroke="([^"]+)"/g)];
    const expected = Array.from(r.strokes, (stroke) =>
      stroke.map(([x, y]) => [x - cx + 240, y - cy + 240].join(',')).join(' '));
    assert.deepEqual(lines.map((m) => m[1]), expected);
    for (const [i, m] of lines.entries()) {
      assert.equal(m[2], i === highlighted[id] ? '#A72D22' : '#244147');
    }
  }
  const heart = rounds.at(-1).strokes;
  assert.ok(heart[1].at(-2)[1] > heart[1][0][1]);
  assert.ok(heart[1].at(-1)[1] < heart[1].at(-2)[1]);
});

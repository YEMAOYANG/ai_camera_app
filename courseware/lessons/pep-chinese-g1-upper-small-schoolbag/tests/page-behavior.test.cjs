// Course-local DOM regressions. Real illustrations and browser acceptance are separate.
const {readFileSync} = require('node:fs');
const {resolve, join} = require('node:path');
const {createRequire} = require('node:module');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const test = require('node:test');

const root = resolve(__dirname, '../../../..');
const source = resolve(__dirname, '..');
const {JSDOM, VirtualConsole} = createRequire(join(root, 'student-web/package.json'))('jsdom');
const lesson = JSON.parse(readFileSync(join(source, 'lesson.json'), 'utf8'));

function openPage(t, sceneKey) {
  const scene = lesson.scenes.find(item => item.key === sceneKey);
  const program = `from courseware.kit.page import page
from pathlib import Path
import sys
stem = Path(sys.argv[1])
print(page(sys.argv[2], *(stem.with_suffix('.' + ext).read_text() for ext in ('html', 'css', 'js'))))
`;
  const html = execFileSync(join(root, 'backend/.venv/bin/python'),
    ['-B', '-c', program, join(source, 'pages', scene.page), scene.title],
    {cwd: root, encoding: 'utf8'});
  let timers = [], nextTimer = 0;
  const errors = [], virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => errors.push(error.message));
  const {window} = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'http://lesson.test/',
    virtualConsole,
    beforeParse(win) {
      win.setTimeout = run => {const id = ++nextTimer; timers.push({id, run}); return id;};
      win.clearTimeout = id => {timers = timers.filter(timer => timer.id !== id);};
    },
  });
  const {$, $$} = window.K;
  function flush() {
    let rounds = 0;
    while (timers.length) {
      assert.ok(rounds++ < 10, 'timer queue must settle');
      const pending = timers;
      timers = [];
      for (const timer of pending) timer.run();
    }
  }
  const click = selector => {
    assert.ok($(selector), selector);
    $(selector).click();
  };
  const state = value => {
    window.dispatchEvent(new window.MessageEvent('message', {data: {type: 'SET_WIDGET_STATE', state: value}}));
  };
  const again = () => {
    assert.ok($('#finish:not(.gone)'));
    click('#btn-again');
    assert.ok($('#finish.gone'));
    assert.equal(window.K.stars, 0);
  };
  t.after(() => {
    assert.deepEqual([...window.K.errs, ...errors], []);
    window.close();
  });
  click('#start-btn');
  return {$, $$, click, state, flush, again, K: window.K};
}

test('three task pictures teach a placement, keep the first miss unmarked, and replay', t => {
  const p = openPage(t, 'find-tool');
  p.state({task: 'ruler', placed: true});
  assert.match(p.$('#tool-clue-image').getAttribute('src'), /task-line/);
  assert.match(p.$('#tool-drop img').getAttribute('src'), /ruler/);
  p.state({phase: 'play'});
  p.click('#tool-pencilcase');
  assert.equal(p.$('#tool-drop').childElementCount, 0);
  assert.equal(p.$$('.teach-hl').length, 0);
  assert.equal(p.K.stars, 0);
  for (let run = 0; run < 2; run++) {
    for (const [clue, tool] of [['erase', 'eraser'], ['line', 'ruler'], ['pens', 'pencilcase']]) {
      assert.match(p.$('#tool-clue-image').getAttribute('src'), new RegExp('task-' + clue));
      p.click('#tool-' + tool);
      assert.match(p.$('#tool-drop img').getAttribute('src'), new RegExp(tool));
      p.flush();
    }
    assert.equal(p.K.stars, 3);
    p.again();
  }
});

test('putting objects in the wrong home leaves them in play; both places finish and reset', t => {
  const p = openPage(t, 'organize-play');
  p.state({items: ['pencil', 'eraser', 'textbook']});
  assert.equal(p.$('#pack-case-items').childElementCount, 2);
  assert.equal(p.$('#pack-bag-items').childElementCount, 1);
  p.state({phase: 'play'});
  p.click('#pack-pencil');
  p.click('#pack-bag');
  assert.equal(p.$('#pack-bag-items').childElementCount, 0);
  assert.equal(p.$$('.teach-hl').length, 0);
  assert.equal(p.K.stars, 0);
  for (let run = 0; run < 2; run++) {
    for (const [item, home] of [['pencil', 'case'], ['textbook', 'bag'], ['eraser', 'case'], ['exercisebook', 'bag']]) {
      p.click('#pack-' + item);
      p.click('#pack-' + home);
      assert.equal(p.$('#pack-' + item).disabled, true);
    }
    assert.equal(p.$('#pack-case-items').childElementCount, 2);
    assert.equal(p.$('#pack-bag-items').childElementCount, 2);
    assert.equal(p.K.stars, 4);
    p.flush();
    p.again();
    assert.equal(p.$$('#pack-targets .pack-received img').length, 0);
  }
});

const groups = [
  ['write-first', [
    ['尺', ['横折', '横', '撇', '捺']],
    ['刀', ['横折钩', '撇']],
  ]],
  ['write-second', [
    ['本', ['横', '竖', '撇', '捺', '横']],
    ['不', ['横', '撇', '竖', '点']],
    ['少', ['竖', '撇', '点', '撇']],
  ]],
];

for (const [scene, rows] of groups) {
  test(scene + ' draws the official stroke order and can complete the whole group twice', t => {
    const p = openPage(t, scene);
    const [last, lastOrder] = rows.at(-1);
    p.state({glyph: last, reveal: lastOrder.length});
    assert.equal(p.$('#schoolbag-glyph').textContent, last);
    assert.equal(p.$$('#schoolbag-grid path[stroke="#2C5147"]').length, lastOrder.length);
    p.state({phase: 'play'});
    p.click('[data-stroke="1"]');
    assert.equal(p.$('#schoolbag-grid').dataset.revealed, '0');
    assert.equal(p.$$('.teach-hl').length, 0);
    for (let run = 0; run < 2; run++) {
      for (const [glyph, order] of rows) {
        assert.equal(p.$('#schoolbag-glyph').textContent, glyph);
        for (let i = 0; i < order.length; i++) {
          const selector = '[data-stroke="' + i + '"]';
          assert.equal(p.$(selector).getAttribute('aria-label'), glyph + '字的' + order[i] + '图');
          const optionPath = p.$(selector + ' path[stroke="#C75B24"]').getAttribute('d');
          p.click(selector);
          const painted = p.$$('#schoolbag-grid path[stroke="#2C5147"]');
          assert.equal(painted.length, i + 1);
          assert.equal(painted.at(-1).getAttribute('d'), optionPath);
          p.flush();
        }
      }
      assert.equal(p.K.stars, rows.length);
      p.again();
    }
  });
}

test('quiz uses independent new images and distributes correct positions', () => {
  const quiz = lesson.scenes.find(scene => scene.type === 'quiz');
  const teaching = JSON.stringify(lesson.scenes.filter(scene => scene !== quiz))
    + ['find-tool', 'organize', 'write-grid'].flatMap(page => ['html', 'js'].map(ext =>
      readFileSync(join(source, 'pages', page + '.' + ext), 'utf8'))).join('');
  const positions = {A: 0, B: 0, C: 0};
  for (const question of quiz.questions) {
    assert.equal(question.answer.length, 1);
    positions[question.answer[0]]++;
    for (const option of Object.values(question.options)) {
      assert.ok(lesson.images[option.visual.image]);
      assert.equal(teaching.includes(option.visual.image), false, option.visual.image);
    }
  }
  assert.deepEqual(positions, {A: 2, B: 2, C: 2});
});

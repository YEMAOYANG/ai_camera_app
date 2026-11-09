const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = path.resolve(__dirname, '..');

for (const [page, answerField, wrong] of [
  ['p05', 'answer', 'unrelated-picture'],
  ['p09', 'answer', '无关字'],
  ['p11', 'group', 'unrelated-home'],
  ['p13', 'answer', 'unrelated-capital'],
]) {
  const game = require(path.join(source, 'pages', `${page}.js`));
  test(`${page}: first wrong answer stays on the task and does not reveal the answer`, () => {
    const state = game.create();
    const response = game.choose(state, wrong);
    assert.equal(response.ok, false);
    assert.equal(state.level, 0);
    assert.deepEqual(state.done, []);
    assert.equal(response.hint.includes(game.tasks[0][answerField]), false);
    assert.equal(Object.hasOwn(response, 'answer'), false);
    assert.equal(state.finished, false);
  });
  test(`${page}: teacher demonstration creates no learner evidence`, () => {
    const state = game.create();
    state.demo = true;
    assert.equal(game.choose(state, game.tasks[0][answerField]).ignored, true);
    assert.deepEqual(state.done, []);
    assert.equal(state.level, 0);
  });
  test(`${page}: all learning tasks can finish, then fresh replay has no old progress`, () => {
    const state = game.create();
    for (const task of game.tasks) assert.equal(game.choose(state, task[answerField]).ok, true);
    assert.equal(state.done.length, game.tasks.length);
    assert.equal(state.finished, true);
    assert.equal(game.choose(state, game.tasks[0][answerField]).ignored, true);
    const replay = game.create();
    assert.equal(replay.level, 0);
    assert.equal(replay.miss, 0);
    assert.equal(replay.finished, false);
    assert.deepEqual(replay.done, []);
  });
}

test('free drawing records an operation and leaves writing and stroke order unobserved', () => {
  const writing = require(path.join(source, 'pages', 'p06.js'));
  const state = writing.create();
  assert.equal(writing.submit(state).ok, false);
  for (let i = 0; i < 10; i++) writing.point(state);
  writing.clear(state);
  assert.equal(state.points, 0);
  assert.equal(writing.submit(state).ok, false);
  for (let word = 0; word < 2; word++) {
    for (let i = 0; i < 10; i++) writing.point(state);
    assert.equal(writing.submit(state).ok, true);
  }
  assert.equal(state.finished, true);
  assert.deepEqual(state.done.map((row) => row.word), ['饱', '抱']);
  for (const observation of state.done) {
    assert.equal(observation.writingQuality, '待观察');
    assert.equal(observation.strokeOrder, '待观察');
  }
  const demonstration = writing.create();
  demonstration.demo = true;
  for (let i = 0; i < 20; i++) writing.point(demonstration);
  assert.equal(demonstration.points, 0);
  assert.equal(writing.submit(demonstration).ignored, true);
});

test('context demonstration is separate from all four pupil prompts', () => {
  const context = require(path.join(source, 'pages', 'p09.js'));
  assert.equal(context.demoTask.phrase, '（　）饭桌旁');
  assert.equal(context.demoTask.answer, '在');
  assert.ok(context.tasks.every(task => task.phrase !== context.demoTask.phrase && task.kind !== context.demoTask.kind));
});

test('quiz uses unseen situations and does not concentrate correct answer positions', () => {
  const lesson = JSON.parse(fs.readFileSync(path.join(source, 'lesson.json')));
  const questions = lesson.scenes.find((scene) => scene.type === 'quiz').questions;
  const counts = {};
  for (const question of questions) {
    assert.equal(question.answer.length, 1);
    assert.ok(question.skill && question.analysis);
    assert.equal(Object.keys(question.options).length, 3);
    counts[question.answer[0]] = (counts[question.answer[0]] || 0) + 1;
  }
  assert.ok(Math.max(...Object.values(counts)) <= questions.length / 2);
  const lessonImages = lesson.scenes.filter((scene) => scene.type === 'slide').flatMap((scene) =>
    Object.entries(scene.data).filter(([key]) => key === 'picture' || key.endsWith('_picture')).map(([, value]) => value));
  for (const image of ['quiz-hug-cat', 'quiz-clear-glass', 'quiz-eat-noodles']) {
    assert.ok(!lessonImages.includes(image));
    assert.ok(JSON.stringify(questions).includes(image));
  }
  assert.ok(!require(path.join(source, 'pages', 'p13.js')).tasks.some((task) => task.label === '伯'));
  const wordCard = questions.find(question => question.id === 'garden5-q5').visual.picture;
  assert.deepEqual(wordCard.groups[0].cells.map(cell => cell.glyph), ['伯', 'bó']);
});

test('semantically rejected paid assets cannot enter the lesson or interactive pages', () => {
  const lesson = JSON.parse(fs.readFileSync(path.join(source, 'lesson.json')));
  const notes = JSON.parse(fs.readFileSync(path.join(source, 'official-notes.json')));
  const pageText = fs.readdirSync(path.join(source, 'pages')).map((file) =>
    fs.readFileSync(path.join(source, 'pages', file), 'utf8')).join('\n');
  for (const rejected of notes.visualReview.rejectedAssets) {
    assert.ok(!Object.hasOwn(lesson.images, rejected.key));
    assert.ok(!JSON.stringify(lesson.scenes).includes(rejected.key));
    assert.ok(!pageText.includes(`__IMG:${rejected.key}__`));
    assert.ok(fs.existsSync(path.join(source, 'assets', `${rejected.key}.png`)));
  }
});

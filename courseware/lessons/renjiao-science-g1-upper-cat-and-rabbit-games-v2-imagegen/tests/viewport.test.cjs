const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function useDrawing(page, name) {
  const K = {ready() {}, game() {}, draw: {rr() {}}};
  const src = readFileSync(path.join(__dirname, '..', 'pages', page + '.js'), 'utf8');
  return vm.runInNewContext(src + '\n' + name, {K, Image: class {
    naturalWidth = 1536;
    naturalHeight = 1024;
  }});
}

function canvas() {
  const drawn = [];
  const context = {save() {}, restore() {}, clip() {}, translate() {}, scale() {},
    drawImage(_image, ...params) { drawn.push(params); }};
  return {context, drawn};
}

test('live animal windows use a centered, aspect-preserving source view even from a 3:2 image', () => {
  const paint = useDrawing('lens', 'paint');
  const {context, drawn} = canvas();
  paint(context, 'test.png', false, [0, 0, 1024, 576], {x: 0, y: 0, w: 1024, h: 576});
  assert.deepEqual(drawn[0], [0, 80, 1536, 864, 0, 0, 1024, 576]);
  paint(context, 'test.png', true, [100, 8, 352, 224], {x: 25, y: 477, w: 352, h: 224});
  assert.deepEqual(drawn[1], [858, 92, 528, 336, 25, 477, 352, 224]);
});

test('a non-square experiment picture remains whole in its square condition card', () => {
  const draw = useDrawing('quiet', 'drawPicture');
  const {context, drawn} = canvas();
  draw(context, 1, 0, 0, 120);
  assert.deepEqual(drawn[0], [0, 20, 120, 80]);
});

test('each registered ear or tail fits inside its solved view and can be reached', () => {
  const sheets = useDrawing('lens', 'sheets');
  const {assets} = JSON.parse(readFileSync(path.join(__dirname, '..', 'asset-sources.json'), 'utf8'));
  const keys = [['cat-gray', 'rabbit-white'], ['cat-orange', 'rabbit-brown']];
  const fields = [['estimatedEarsInNormalizedView', 'estimatedEarsInNormalizedView'],
    ['estimatedTailInNormalizedView', 'estimatedMirroredTailInNormalizedView']];
  sheets.forEach((sheet, level) => {
    const [width, height] = sheet.crop;
    for (let panel = 0; panel < 2; panel++) {
      const review = assets[keys[level][panel]].staticReview;
      const [x, y, w, h] = review[fields[level][panel]];
      const cx = sheet.targets[panel], cy = sheet.height;
      assert.ok(cx >= width / 2 && cx <= 1024 - width / 2);
      assert.ok(x >= cx - width / 2 && x + w <= cx + width / 2);
      assert.ok(y >= cy - height / 2 && y + h <= cy + height / 2);
    }
  });
});

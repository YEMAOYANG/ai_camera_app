import assert from 'node:assert/strict';
import test from 'node:test';
import { createContext, runInContext } from 'node:vm';
import { clickProjectedBrowserInput, projectBrowserInput } from '../projected_browser_input.mjs';

const defaultStyle = {
  width: '1280px', height: '720px', boxSizing: 'content-box', visibility: 'visible',
  transform: 'none', rotate: 'none', perspective: 'none', scale: 'none',
  borderLeftWidth: '0px', borderRightWidth: '0px', borderTopWidth: '0px', borderBottomWidth: '0px',
  paddingLeft: '0px', paddingRight: '0px', paddingTop: '0px', paddingBottom: '0px',
};

function frameFixture(width, height, rect, style = {}) {
  const element = {
    rect,
    style,
    isConnected: true,
    disabled: false,
    parentElement: null,
    matches() { return this.disabled; },
    getBoundingClientRect() { return this.rect; },
    contains(hit) { return hit === this; },
  };
  const document = {
    elementFromPoint(x, y) {
      const { left, top, width: boxWidth, height: boxHeight } = element.rect;
      if (x < 0 || x >= width || y < 0 || y >= height) return null;
      return x >= left && x < left + boxWidth && y >= top && y < top + boxHeight ? element : null;
    },
  };
  const context = createContext({
    document, window: { innerWidth: width, innerHeight: height },
    getComputedStyle: node => ({ ...defaultStyle, ...node.style }),
    DOMMatrixReadOnly: class {
      constructor(value) {
        this.is2D = value.startsWith('matrix(');
        [this.a, this.b, this.c, this.d] = value.slice(7, -1).split(',').map(Number);
      }
    },
  });
  const frame = {
    parentFrame() { return this.parent ?? null; },
    async frameElement() { return this.container; },
  };
  const handle = {
    async evaluate(callback, arg) {
      context.element = element;
      context.arg = arg;
      return runInContext('(' + callback.toString() + ')(element, arg)', context);
    },
    async ownerFrame() { return frame; },
    async dispose() {},
  };
  return { frame, element, handle, document };
}

function link(child, parent) {
  child.frame.parent = parent.frame;
  child.frame.container = parent.handle;
}

function pageFixture(root) {
  const events = [];
  return {
    events,
    mainFrame: () => root.frame,
    mouse: {
      async move(x, y) { events.push(['move', x, y]); },
      async click(x, y) { events.push(['click', x, y]); },
    },
  };
}

const locatorFor = fixture => ({ async elementHandle() { return fixture.handle; } });
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 0.02, `${actual} != ${expected}`);

test('projects the observed Walk into Science point through two frames', async () => {
  const root = frameFixture(1280, 800, { left: 0, top: 64, width: 1280, height: 736 }, { height: '736px' });
  const classroom = frameFixture(1280, 736, { left: 234.65625, top: 56, width: 810.666626, height: 456 });
  const game = frameFixture(1280, 720, { left: 505.953125, top: 428, width: 268.09375, height: 96 });
  link(classroom, root);
  link(game, classroom);
  const page = pageFixture(root);
  const result = await clickProjectedBrowserInput(page, game.frame, locatorFor(game));
  near(result.layers[1].point.y, 357.4667);
  near(result.point.x, 639.98956);
  near(result.point.y, 421.46667);
  assert.deepEqual(page.events.map(event => event[0]), ['move', 'click']);
  near(page.events[1][1], result.point.x);
  near(page.events[1][2], result.point.y);
  // The old locator actually sent y=532 in the classroom, beyond its iframe.
  assert.notEqual(classroom.document.elementFromPoint(874.65, 532), classroom.element);
});

test('projects the observed Numbers shutter point in the direct classroom', async () => {
  const root = frameFixture(1280, 800, { left: 227.546875, top: 56, width: 824.888916, height: 464 });
  const game = frameFixture(1280, 720, { left: 1110, top: 609, width: 150, height: 94 });
  link(game, root);
  const page = pageFixture(root);
  const result = await projectBrowserInput(page, game.frame, locatorFor(game));
  near(result.point.x, 991.21356678);
  near(result.point.y, 478.75555556);
  assert.deepEqual(page.events, []);
});

test('projects through scaled borders and padding, including a border-box sizing rule', async () => {
  const root = frameFixture(700, 500, { left: 25, top: 40, width: 327, height: 185 }, {
    width: '654px', height: '370px', boxSizing: 'border-box',
    borderLeftWidth: '4px', borderRightWidth: '4px', paddingLeft: '2px', paddingRight: '4px',
    borderTopWidth: '6px', borderBottomWidth: '4px', transform: 'matrix(0.5, 0, 0, 0.5, 0, 0)',
  });
  const game = frameFixture(640, 360, { left: 300, top: 170, width: 40, height: 20 });
  link(game, root);
  const result = await projectBrowserInput(pageFixture(root), game.frame, locatorFor(game));
  assert.equal(result.point.x, 188);
  assert.equal(result.point.y, 133);
  assert.equal(result.layers[1].contentBox.left, 28);
});

test('rejects an overlay in the parent before it sends any pointer input', async () => {
  const root = frameFixture(1000, 800, { left: 20, top: 20, width: 640, height: 360 });
  const game = frameFixture(1280, 720, { left: 300, top: 170, width: 40, height: 20 });
  link(game, root);
  root.document.elementFromPoint = () => ({});
  const page = pageFixture(root);
  await assert.rejects(clickProjectedBrowserInput(page, game.frame, locatorFor(game)), /exact enclosing iframe/);
  assert.deepEqual(page.events, []);
});

test('rejects a non-axis-aligned ancestor before pointer input', async () => {
  const root = frameFixture(1000, 800, { left: 20, top: 20, width: 640, height: 360 });
  root.element.parentElement = { style: { transform: 'matrix(0.5, 0.1, 0, 0.5, 0, 0)' } };
  const game = frameFixture(1280, 720, { left: 300, top: 170, width: 40, height: 20 });
  link(game, root);
  const page = pageFixture(root);
  await assert.rejects(clickProjectedBrowserInput(page, game.frame, locatorFor(game)), /exact enclosing iframe/);
  assert.deepEqual(page.events, []);
});

test('rejects a mismatched frame, disabled target, or clipped center before pointer input', async () => {
  const root = frameFixture(640, 360, { left: 100, top: 150, width: 40, height: 20 });
  const other = frameFixture(640, 360, { left: 100, top: 150, width: 40, height: 20 });
  const page = pageFixture(root);
  await assert.rejects(clickProjectedBrowserInput(page, root.frame, locatorFor(other)), /supplied frame/);
  root.element.disabled = true;
  await assert.rejects(clickProjectedBrowserInput(page, root.frame, locatorFor(root)), /not actionable/);
  root.element.disabled = false;
  root.element.rect.left = 625;
  await assert.rejects(clickProjectedBrowserInput(page, root.frame, locatorFor(root)), /not actionable/);
  assert.deepEqual(page.events, []);
});

test('checks the hit again after hover and declines to click a shifted target', async () => {
  const root = frameFixture(640, 360, { left: 100, top: 150, width: 40, height: 20 });
  const page = pageFixture(root);
  const move = page.mouse.move;
  page.mouse.move = async (x, y) => {
    await move(x, y);
    root.element.rect.left += 8;
  };
  await assert.rejects(clickProjectedBrowserInput(page, root.frame, locatorFor(root)), /moved during hover/);
  assert.deepEqual(page.events.map(event => event[0]), ['move']);
});

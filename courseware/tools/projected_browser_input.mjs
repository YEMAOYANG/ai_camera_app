// Browser automation can report an unscaled locator position for a sandboxed
// iframe. Project through the measured content box of each enclosing frame.

function readTarget(element) {
  if (!element.isConnected || element.matches(':disabled, [aria-disabled="true"]')) return null;
  const style = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  if (style.visibility !== 'visible' || rect.width <= 0 || rect.height <= 0) return null;
  const point = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  if (!element.contains(document.elementFromPoint(point.x, point.y))) return null;
  return { point, viewport: { width: window.innerWidth, height: window.innerHeight } };
}

function readParentProjection(element, child) {
  for (let node = element; node; node = node.parentElement) {
    const style = getComputedStyle(node);
    if (style.rotate && style.rotate !== 'none') return null;
    if (style.perspective && style.perspective !== 'none') return null;
    if (style.scale && style.scale !== 'none') {
      const factors = style.scale.split(/\s+/).map(Number);
      if (factors.length > 2 || factors.some(factor => !Number.isFinite(factor) || factor <= 0)) return null;
    }
    if (style.transform && style.transform !== 'none') {
      const matrix = new DOMMatrixReadOnly(style.transform);
      if (!matrix.is2D || matrix.a <= 0 || matrix.d <= 0 ||
          Math.abs(matrix.b) > 1e-6 || Math.abs(matrix.c) > 1e-6) return null;
    }
  }
  const rect = element.getBoundingClientRect();
  const css = getComputedStyle(element);
  const sizes = [
    css.width, css.height, css.borderLeftWidth, css.paddingLeft,
    css.borderRightWidth, css.paddingRight, css.borderTopWidth,
    css.paddingTop, css.borderBottomWidth, css.paddingBottom,
  ].map(value => Number.parseFloat(value));
  if (!sizes.every(Number.isFinite)) return null;
  const [width, height, left, padLeft, right, padRight, top, padTop, bottom, padBottom] = sizes;
  const horizontal = left + padLeft + right + padRight;
  const vertical = top + padTop + bottom + padBottom;
  const contentWidth = css.boxSizing === 'border-box' ? width - horizontal : width;
  const contentHeight = css.boxSizing === 'border-box' ? height - vertical : height;
  const { point, viewport } = child;
  if (Math.min(contentWidth, contentHeight, rect.width, rect.height, viewport.width, viewport.height) <= 0 ||
      point.x < 0 || point.x >= viewport.width || point.y < 0 || point.y >= viewport.height) return null;
  const scaleX = rect.width / (contentWidth + horizontal);
  const scaleY = rect.height / (contentHeight + vertical);
  const contentBox = {
    left: rect.left + (left + padLeft) * scaleX,
    top: rect.top + (top + padTop) * scaleY,
    width: contentWidth * scaleX,
    height: contentHeight * scaleY,
  };
  const projected = {
    x: contentBox.left + point.x * contentBox.width / viewport.width,
    y: contentBox.top + point.y * contentBox.height / viewport.height,
  };
  if (document.elementFromPoint(projected.x, projected.y) !== element) return null;
  return {
    point: projected,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    contentBox,
  };
}

async function resolveTarget(page, frame, element) {
  if (await element.ownerFrame() !== frame) {
    throw new Error('Projected input target does not belong to the supplied frame');
  }
  const target = await element.evaluate(readTarget);
  if (!target) throw new Error('Projected input target is not actionable at its visible center');

  let current = frame;
  let projection = target;
  const layers = [target];
  while (current !== page.mainFrame()) {
    const parent = current.parentFrame();
    if (!parent) throw new Error('Projected input frame does not belong to the page');
    const iframe = await current.frameElement();
    try {
      projection = await iframe.evaluate(readParentProjection, projection);
    } finally {
      await iframe.dispose();
    }
    if (!projection) throw new Error('Projected input did not hit the exact enclosing iframe');
    layers.push(projection);
    current = parent;
  }
  return { point: projection.point, layers };
}

// Callers can use this read-only projection before a normal pointer hold.
export async function projectBrowserInput(page, frame, locator) {
  const element = await locator.elementHandle();
  if (!element) throw new Error('Projected input target is missing');
  try {
    return await resolveTarget(page, frame, element);
  } finally {
    await element.dispose();
  }
}

// An independent event/state observer still needs to confirm the click result.
export async function clickProjectedBrowserInput(page, frame, locator) {
  const element = await locator.elementHandle();
  if (!element) throw new Error('Projected input target is missing');
  try {
    const before = await resolveTarget(page, frame, element);
    await page.mouse.move(before.point.x, before.point.y);
    const after = await resolveTarget(page, frame, element);
    if (Math.hypot(after.point.x - before.point.x, after.point.y - before.point.y) >= 1) {
      throw new Error('Projected input moved during hover');
    }
    await page.mouse.click(after.point.x, after.point.y);
    return after;
  } finally {
    await element.dispose();
  }
}

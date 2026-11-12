import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../../../../student-web/package.json', import.meta.url));
const sharp = require('sharp');
const asset = name => fileURLToPath(new URL('../assets/' + name + '.png', import.meta.url));
const master = name => fileURLToPath(new URL(name + '.png', import.meta.url));

const shapes = {
  'q-tip-cross': '<path d="M121 62h38v32h32v38h-32v32h-38v-32H89V94h32z"/>',
  'q-tip-flat': '<rect x="79" y="96" width="122" height="34" rx="4"/>',
  'q-tip-hex': '<path d="M105 65h70l35 48-35 48h-70l-35-48z"/>',
};

function tip(shape) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="280" height="226" viewBox="0 0 280 226">
    <rect width="280" height="226" fill="#f8eedb"/>
    <circle cx="140" cy="113" r="76" fill="#b4beb9" stroke="#526760" stroke-width="8"/>
    <g fill="#345249" stroke="#253f38" stroke-width="2">${shape}</g>
  </svg>`;
}

for (const [key, shape] of Object.entries(shapes)) {
  await sharp(Buffer.from(tip(shape))).png().toFile(asset(key));
}
const slot = tip(shapes['q-tip-cross']).replace('#f8eedb', '#e3ecd5').replace('#b4beb9', '#9faeaa');
await sharp(Buffer.from(slot)).png().toFile(asset('q-slot-cross'));

const circle = `<svg xmlns="http://www.w3.org/2000/svg" width="280" height="226" viewBox="0 0 280 226">
  <rect width="280" height="226" fill="#f8eedb"/>
  <rect x="52" y="25" width="176" height="176" rx="12" fill="#fffdf6" stroke="#a48d65" stroke-width="4"/>
  <circle cx="140" cy="113" r="51" fill="none" stroke="#416c5b" stroke-width="8"/>
</svg>`;
await sharp(Buffer.from(circle)).png().toFile(asset('circle-task'));
const triangle = circle.replace('<circle cx="140" cy="113" r="51" fill="none" stroke="#416c5b" stroke-width="8"/>',
  '<path d="M140 57l57 98H83z" fill="none" stroke="#416c5b" stroke-width="8" stroke-linejoin="round"/>');
await sharp(Buffer.from(triangle)).png().toFile(asset('triangle-task'));

// Same ImageGen master and same tool. Remove the practice screw to make the
// matching game compare the tool with a genuinely separate task illustration.
await sharp(master('tool-orthogonal-views'))
  .extract({ left: 1197, top: 175, width: 394, height: 155 })
  .png().toFile(asset('driver-icon'));

// The distractor repeats the very same position in both panels.
const leftBag = await sharp(asset('q-bag-fair'))
  .extract({ left: 0, top: 0, width: 236, height: 322 }).png().toBuffer();
await sharp({ create: { width: 484, height: 322, channels: 3, background: '#f8eedb' } })
  .composite([{ input: leftBag, left: 0, top: 0 }, { input: leftBag, left: 248, top: 0 }])
  .png().toFile(asset('q-bag-same-position'));

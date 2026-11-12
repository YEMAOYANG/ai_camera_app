import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../../../../student-web/package.json', import.meta.url));
const sharp = require('sharp');
const asset = name => fileURLToPath(new URL('../assets/' + name + '.png', import.meta.url));
const diagrams = {};

function diagram(key, width, height, lines, portraits) {
  diagrams[key] = {width, height, lines, portraits};
}

function relation(key, speaker, relative, middle) {
  const gap = middle
    ? [[speaker, 24, 83, 118], [middle, 196, 83, 118], [relative, 368, 83, 118]]
    : [[speaker, 52, 73, 139], [relative, 315, 73, 139]];
  diagram(key, 510, 266,
    '<path d="M101 145H412" stroke="#417b72" stroke-width="11" stroke-linecap="round"/>' +
    (middle ? '<circle cx="169" cy="145" r="6" fill="#fff3cc"/><circle cx="340" cy="145" r="6" fill="#fff3cc"/>' : ''),
    gap);
}

function distance(key, speaker, relative, far) {
  const destination = far ? 414 : 246;
  diagram(key, 550, 273,
    '<path d="M43 220H509" stroke="#d2a674" stroke-width="10" stroke-linecap="round"/>' +
    '<path d="M94 235H' + destination + '" stroke="#365f58" stroke-width="8" stroke-linecap="round" stroke-dasharray="4 18"/>' +
    '<path d="M' + (destination - 25) + ' 222l25 13-25 13" fill="none" stroke="#365f58" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>',
    [[speaker, 27, 73, 134], [relative, destination - 67, 73, 134]]);
}

function station(key, speaker, far) {
  const destination = far ? 230 : 159;
  diagram(key, 280, 254,
    '<path d="M71 205H' + destination + '" stroke="#365f58" stroke-width="12" stroke-dasharray="6 17" stroke-linecap="round"/>' +
    '<path d="M' + destination + ' 180v50" stroke="#365f58" stroke-width="10" stroke-linecap="round"/>' +
    '<circle cx="' + destination + '" cy="118" r="29" fill="#f7d892" stroke="#8b563e" stroke-width="8"/>' +
    '<path d="M' + destination + ' 95v46" stroke="#b0774e" stroke-width="5"/>',
    [[speaker, 12, 49, 119]]);
}

relation('relation-grandpa-a', 'host-a', 'grandpa-a', 'mother-a');
relation('relation-father-mother', 'mother-a', 'grandpa-a');
relation('quiz-mother-relation', 'quiz-host-a', 'quiz-mother');
relation('quiz-grandma-relation', 'quiz-host-a', 'quiz-grandma', 'quiz-mother');
relation('quiz-other-father-relation', 'quiz-host-a', 'quiz-father');

distance('near-father-a', 'host-a', 'father-a', false);
distance('far-father-a', 'host-a', 'father-a', true);
distance('near-friend-a', 'host-a', 'friend-a', false);
distance('quiz-grandma-near', 'quiz-host-a', 'quiz-grandma', false);
distance('quiz-grandma-far', 'quiz-host-a', 'quiz-grandma', true);
distance('quiz-grandpa-near', 'quiz-host-a', 'quiz-grandpa', false);
distance('quiz-b-father-far', 'quiz-host-b', 'quiz-father-b', true);
distance('quiz-a-father-far', 'quiz-host-a', 'quiz-father', true);
distance('quiz-b-father-wrong', 'quiz-host-b', 'quiz-father', true);

station('near-a', 'host-a', false);
station('far-a', 'host-a', true);
station('near-b', 'host-b', false);
station('far-b', 'host-b', true);
station('near-mother', 'mother-a', false);
station('far-mother', 'mother-a', true);

diagram('family-tree-a', 630, 420,
  '<g fill="none" stroke="#417b72" stroke-width="11" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M85 92v73h240v61M325 92v73M325 226v49h-120v58M85 226v49h120"/>' +
  '<path d="M205 345h324" stroke="#b0734d" stroke-dasharray="8 21"/></g>',
  [['grandpa-a', 31, 22, 108], ['grandma-a', 271, 22, 108],
    ['father-a', 31, 170, 108], ['mother-a', 271, 170, 108],
    ['host-a', 151, 299, 108], ['friend-a', 475, 299, 108]]);

diagram('quiz-welcome-chart', 644, 433,
  '<g fill="none" stroke="#417b72" stroke-width="9" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M67 64v57h189v74M256 64v131M67 195v72h93v78M256 195v72h-96"/>' +
  '<path d="M160 355h203" stroke="#b0734d" stroke-dasharray="8 21"/><path d="M547 205v137"/></g>',
  [['quiz-grandpa', 20, 13, 94], ['quiz-grandma', 209, 13, 94],
    ['quiz-father', 20, 150, 94], ['quiz-mother', 209, 150, 94],
    ['quiz-host-a', 113, 305, 94], ['quiz-friend', 316, 305, 94],
    ['quiz-father-b', 500, 150, 94], ['quiz-host-b', 500, 305, 94]]);

function route(key, first, second, isNearFirst, isNearSecond) {
  const left = isNearFirst ? 131 : 174;
  const right = isNearSecond ? 395 : 438;
  diagram(key, 510, 266,
    '<rect x="11" y="32" width="224" height="201" rx="21" fill="#eadfc4"/>' +
    '<rect x="275" y="32" width="224" height="201" rx="21" fill="#eadfc4"/>' +
    '<path d="M237 133h34m-12-12 12 12-12 12" fill="none" stroke="#365f58" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<path d="M59 171H' + left + 'M323 171H' + right + '" stroke="#365f58" stroke-width="7" stroke-dasharray="4 13" stroke-linecap="round"/>',
    [['quiz-host-a', 22, 77, 74], [first, left - 27, 86, 57],
      ['quiz-host-a', 286, 77, 74], [second, right - 27, 86, 57]]);
}
route('quiz-route-correct', 'quiz-grandpa', 'quiz-friend', false, true);
route('quiz-route-near-first', 'quiz-grandpa', 'quiz-friend', true, true);
route('quiz-route-reverse', 'quiz-friend', 'quiz-grandpa', true, false);

function tile(key, speaker, visitor, middle) {
  const tail = middle ? 'M67 247h148v-38' : 'M69 255h150v-50';
  const stroke = key === 'tile-friend-a'
    ? 'stroke="#b0734d" stroke-dasharray="8 15"'
    : 'stroke="#417b72"';
  const faces = [[speaker, 16, 202, 89], [visitor, 105, 18, 200]];
  if (middle) faces.push([middle, 114, 210, 73]);
  diagram(key, 320, 310, '<path d="' + tail + '" ' + stroke +
    ' fill="none" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>', faces);
}
tile('tile-father-a','host-a','father-a');
tile('tile-mother-a','host-a','mother-a');
tile('tile-grandpa-a','host-a','grandpa-a','mother-a');
tile('tile-grandma-a','host-a','grandma-a','mother-a');
tile('tile-friend-a','host-a','friend-a');
tile('tile-father-mother','mother-a','grandpa-a');
tile('tile-father-b','host-b','father-b');

diagram('family-cards-opening', 590, 400,
  '<rect x="93" y="14" width="400" height="365" rx="25" fill="#263f38"/>' +
  '<path d="M294 155v93m-22-24 22 24 22-24" fill="none" stroke="#ffdc95" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>',
  [['host-a', 246, 42, 96], ['tile-mother-a', 132, 265, 96],
    ['tile-father-a', 361, 265, 96]]);

diagram('delivery-opening', 590, 400,
  '<rect x="86" y="15" width="418" height="370" rx="29" fill="#b8cd98"/>' +
  '<rect x="86" y="150" width="418" height="89" rx="7" fill="#68766f"/>' +
  '<path d="M100 196h393" stroke="#fff3d8" stroke-width="6" stroke-dasharray="34 22"/>' +
  '<path d="M300 287V120m-18 18 18-18 18 18" fill="none" stroke="#754a3d" stroke-width="10" stroke-dasharray="8 15" stroke-linecap="round" stroke-linejoin="round"/>',
  [['near-a', 125, 32, 91], ['far-a', 365, 32, 91], ['lantern-van', 252, 268, 96], ['father-a', 365, 267, 91]]);

if (process.argv.includes('--describe')) {
  const metadata = Object.fromEntries(Object.entries(diagrams).map(([key, value]) =>
    [key, [...new Set(value.portraits.map(([portrait]) => portrait))]]));
  console.log(JSON.stringify(metadata));
} else {
  for (const [key, {width, height, lines, portraits}] of Object.entries(diagrams)) {
    const background = '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '">' +
      '<rect width="100%" height="100%" fill="#fff3d8"/>' + lines + '</svg>';
    const layers = [];
    for (let i = 0; i < portraits.length; i++) {
      const [name, left, top, size] = portraits[i];
      const image = await sharp(asset(name)).resize(size, size, {fit:'cover'}).png().toBuffer();
      const chart = key === 'quiz-welcome-chart' || key === 'family-tree-a';
      const speaker = chart ? i === 4 || (key === 'quiz-welcome-chart' && i === 7)
        : i === 0 || (key.startsWith('quiz-route-') && i === 2);
      const frame = '<svg xmlns="http://www.w3.org/2000/svg" width="' + (size + 12) + '" height="' + (size + 12) + '">' +
        '<rect x="3" y="3" width="' + (size + 6) + '" height="' + (size + 6) + '" rx="13" fill="' +
        (speaker ? '#315f58' : '#b78358') + '"/></svg>';
      layers.push({input:Buffer.from(frame), left:left - 6, top:top - 6}, {input:image, left, top});
    }
    await sharp(Buffer.from(background)).composite(layers).png().toFile(asset(key));
  }
}

import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../../../../student-web/package.json', import.meta.url));
const sharp = require('sharp');
const file = name => fileURLToPath(new URL('../assets/' + name + '.png', import.meta.url));
const art = {};
const pictures = new Map();
const ink = '#304f46';
const paper = '#fbefce';
const colors = {
  pine: ['#82ab92','#6c9b83','#4b7866'],
  aqua: ['#a6d0c3','#7aafae','#558987'],
  orange: ['#ffd393','#edab65','#b97545'],
  blue: ['#bdd5e4','#87acc7','#5e8caa'],
};
const points = values => values.map(pair => pair.map(n => Number(n.toFixed(2))).join(',')).join(' ');
const polygon = (values, fill, stroke = ink, width = 2.8, extra = '') =>
  '<polygon points="' + points(values) + '" fill="' + fill + '" stroke="' + stroke +
  '" stroke-width="' + width + '" stroke-linejoin="round" ' + extra + '/>';
const ellipse = (x,y,rx,ry,fill,stroke=ink,width=2.8) =>
  '<ellipse cx="' + x + '" cy="' + y + '" rx="' + rx + '" ry="' + ry +
  '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + width + '"/>';
const line = (x,y,xx,yy,fill=ink,width=4) =>
  '<path d="M'+x+' '+y+'L'+xx+' '+yy+'" stroke="'+fill+'" stroke-width="'+width+'" stroke-linecap="round"/>';
const ground = (x,y,w) => line(x,y,x+w,y,'#9d9d70',4);
const arrow = (x,y,xx,yy,color=ink) => {
  const angle = Math.atan2(yy-y,xx-x);
  const heads = [angle-.56,angle+.56].map(a => [xx-16*Math.cos(a),yy-16*Math.sin(a)]);
  return line(x,y,xx,yy,color,5) + polygon([[xx,yy],...heads],color,color,1);
};
const project = (origin,unit) => ([x,y,z]) => [
  origin[0]+unit*(x+.49*y), origin[1]-unit*(z+.34*y),
];

function sides(x,y,z,w,d,h) {
  return [
    [[x,y,z+h],[x+w,y,z+h],[x+w,y+d,z+h],[x,y+d,z+h]],
    [[x,y,z],[x+w,y,z],[x+w,y,z+h],[x,y,z+h]],
    [[x+w,y,z],[x+w,y+d,z],[x+w,y+d,z+h],[x+w,y,z+h]],
  ];
}

function box(origin,unit,[x,y,z,w,d,h],color='pine',guide=false) {
  const to = project(origin,unit);
  return sides(x,y,z,w,d,h).map((face,i) => polygon(face.map(to),
    guide ? '#fff7e8' : colors[color][i],guide ? '#984828' : ink,guide ? 4.6 : 2.7,
    guide ? 'fill-opacity=".38" stroke-dasharray="8 5"' : '')).join('');
}

function grid(w,d,h) {
  return Array.from({length:w*d*h},(_,i) => [i%w,Math.floor(i/w)%d,Math.floor(i/(w*d))]);
}
function voxels(origin,unit,blocks,palette=()=> 'aqua') {
  const occupied = new Set(blocks.map(p=>p.join(',')));
  const to = project(origin,unit);
  return [...blocks].sort((a,b)=>(a[0]-a[1]+a[2])-(b[0]-b[1]+b[2])).map(([x,y,z]) => {
    const neighbors = [[x,y,z+1],[x,y-1,z],[x+1,y,z]];
    return sides(x,y,z,1,1,1).map((face,i) => occupied.has(neighbors[i].join(',')) ? '' :
      polygon(face.map(to),colors[palette(x,y,z)][i])).join('');
  }).join('');
}

function cylinder(x,bottom,r,h,color='pine',guide=false) {
  const [top,front,side] = colors[color];
  const y=bottom-h;
  const ry=r*.35;
  const body='M'+(x-r)+' '+y+'V'+bottom+'A'+r+' '+ry+' 0 0 0 '+(x+r)+' '+bottom+'V'+y+'Z';
  if (guide) return '<path d="'+body+'" fill="#fff7e8" fill-opacity=".5" stroke="#984828" stroke-width="4.6" stroke-dasharray="8 5"/>'+
    ellipse(x,y,r,ry,'#fff7e8','#984828',4.1);
  return '<path d="'+body+'" fill="'+front+'" stroke="'+ink+'" stroke-width="2.8"/>'+
    '<path d="M'+(x+r*.66)+' '+(y+3)+'V'+(bottom+ry*.52)+'" stroke="'+side+'" stroke-width="'+(r*.25)+'" opacity=".48"/>'+
    ellipse(x,y,r,ry,top);
}

function lying(x,y,r,length,color='pine') {
  const [top,front,side]=colors[color];
  const back=x-length;
  const body='M'+back+' '+(y-r)+'H'+x+'V'+(y+r)+'H'+back+
    'A'+(r*.31)+' '+r+' 0 0 1 '+back+' '+(y-r)+'Z';
  return '<path d="'+body+'" fill="'+front+'" stroke="'+ink+'" stroke-width="2.8"/>'+
    line(back+4,y-r*.47,x-7,y-r*.47,top,4)+ellipse(x,y,r*.31,r,top,side);
}
function ball(x,y,r,alternate=false) {
  const stops=alternate?['#fff0ce','#eeb870','#b87648']:['#f4fff1','#9ec7a2','#59856f'];
  return '<defs><radialGradient id="round" cx="32%" cy="25%" r="75%">'+
    '<stop offset="0" stop-color="'+stops[0]+'"/><stop offset=".61" stop-color="'+stops[1]+'"/>'+
    '<stop offset="1" stop-color="'+stops[2]+'"/></radialGradient></defs>'+
    ellipse(x,y,r,r,'url(#round)');
}

function add(name,width,height,draw,inputs=[]) {
  art[name]=inputs;
  pictures.set(name,{width,height,draw});
}
const square = (name,draw) => add(name,230,230,draw);

square('sample-long',box([36,159],85,[0,0,0,1.56,.6,.59],'aqua'));
square('sample-cube',box([53,166],89,[0,0,0,1,1,1],'aqua'));
square('sample-cylinder',cylinder(114,172,49,104,'aqua'));
square('sample-ball',ball(115,113,59));
square('token-long',box([61,193],90,[0,0,0,.66,.83,1.52],'orange'));
square('token-cube',box([53,164],86,[0,0,0,1,1,1],'blue'));
square('token-cylinder',lying(160,115,48,95,'orange'));
square('token-ball',ball(115,113,54,true));
square('q-long',box([54,188],84,[0,0,0,.8,.8,1.52],'blue'));
square('q-cube',box([52,173],88,[0,0,0,1,1,1],'pine'));
square('q-cylinder',lying(166,114,45,98,'blue'));
square('q-ball',ball(115,115,62,true));
square('q-cylinder-upright',ground(32,181,168)+cylinder(112,163,49,100,'orange'));
square('q-cylinder-side',ground(27,181,179)+lying(166,132,49,100,'orange'));
square('q-cylinder-tilt',ground(27,188,180)+
  '<g transform="rotate(31 114 139)">'+cylinder(114,162,49,100,'orange')+'</g>');

add('flat-box-positions',560,300,
    ground(28,237,503)+box([53,235],96,[0,0,0,1.45,.85,.56],'orange')+
    arrow(244,179,312,179)+box([347,235],96,[0,0,0,.56,.85,1.45],'orange'));
add('flat-cube-faces',560,300,
    box([59,211],123,[0,0,0,1,1,1],'blue')+
    arrow(253,150,320,150)+box([352,211],123,[0,0,0,1,1,1],'pine'));
add('cylinder-positions',560,300,
    ground(22,241,512)+cylinder(122,222,54,124,'pine')+
    lying(467,187,54,124,'pine')+arrow(442,244,389,272,'#a7653d'));
add('ball-directions',560,300,
    ground(58,222,439)+ball(280,158,65,true)+arrow(191,217,100,217)+arrow(371,217,462,217));

function stack(name,first,second,offset,fill='pine') {
  square(name,cylinder(114,186,first,50,fill)+cylinder(114+offset,136,second,55,'orange'));
}
stack('stack-aligned',49,49,0);
stack('stack-offset',49,49,26);
stack('stack-mismatch',55,37,0);
stack('q-stack-aligned',43,43,0,'blue');
stack('q-stack-offset',44,44,-29,'blue');
stack('q-stack-mismatch',41,61,0,'blue');

add('two-cubes-long',560,280,
    voxels([36,208],69,grid(2,1,1),(x)=>x===0?'aqua':'orange')+
    arrow(226,155,286,155)+box([327,209],76,[0,0,0,2,1,1],'pine'));
add('rectangles-join',560,280,
    box([45,210],67,[0,1.62,0,2,1,1],'orange')+
    box([45,210],67,[0,0,0,2,1,1],'pine')+
    arrow(247,147,304,147)+
    box([336,210],69,[0,1,0,2,1,1],'orange')+box([336,210],69,[0,0,0,2,1,1],'pine'));
add('cube-layers',620,385,
    voxels([53,323],81,grid(2,2,1),()=> 'pine')+
    voxels([53,177],81,grid(2,2,1),()=> 'orange')+
    arrow(318,202,370,202)+
    voxels([406,318],63,grid(2,2,2),(x,y,z)=>z===0?'pine':'orange'));
square('q-cube-eight',voxels([36,176],52,grid(2,2,2),(x,y,z)=>z===0?'aqua':'orange'));
square('q-cube-flat',voxels([35,168],53,grid(2,2,1),(x,y)=>y===0?'aqua':'orange'));
square('q-eight-slab',voxels([17,164],37,grid(4,2,1),(x,y)=>y===0?'aqua':'orange'));

const gapBoards={
  'base-thin':{cylinder:41},'base-wide':{cylinder:62},
  'base-four':{size:[2,2,1],goal:[2,2,2]},
  'base-row':{size:[3,1,1],goal:[3,1,2]},
  'base-pair':{size:[1,2,1],goal:[1,2,2]},
  'base-wall':{size:[2,1,1],goal:[2,1,3]},
  'base-beam':{size:[4,1,1],goal:[4,1,2]},
};
const pieces={
  'piece-thin':{cylinder:41},'piece-wide':{cylinder:62},
  'piece-four':{size:[2,2,1]},'piece-row':{size:[3,1,1]},'piece-pair':{size:[1,2,1]},
  'piece-wall':{size:[2,1,2]},'piece-beam':{size:[4,1,1]},
};
function sceneOrigin(size,bottom=184) {
  return [Math.round(115-(size[0]+.49*size[1])*20),bottom];
}
for (const [key,value] of Object.entries(pieces)) {
  if (value.cylinder) square(key,cylinder(115,160,value.cylinder,50,'orange'));
  else square(key,voxels(sceneOrigin(value.size,161),40,grid(...value.size),()=> 'orange'));
}
for (const [key,value] of Object.entries(gapBoards)) {
  if (value.cylinder) {
    square(key,cylinder(115,181,value.cylinder,50,'aqua')+cylinder(115,131,value.cylinder,50,'orange',true));
    square(key.replace('base-','built-'),
      cylinder(115,181,value.cylinder,50,'aqua')+cylinder(115,131,value.cylinder,50,'orange'));
  } else {
    const [w,d,h]=value.size;
    const [, ,goalHeight]=value.goal;
    const origin=sceneOrigin(value.goal);
    square(key,voxels(origin,40,grid(w,d,h))+
      box(origin,40,[0,0,h,w,d,goalHeight-h],'orange',true));
    square(key.replace('base-','built-'),
      voxels(origin,40,grid(...value.goal),(x,y,z)=>z<h?'aqua':'orange'));
  }
}

const target = grid(3,2,1);
const known = [[0,0,0],[1,0,0]];
const remainder = target.filter(p=>!known.some(q=>q.join(',')===p.join(',')));
square('q-gap-plan',
  box([26,169],46,[0,0,0,3,2,1],'orange',true)+voxels([26,169],46,known,()=> 'pine'));
square('q-fit-piece',voxels([26,169],46,remainder,()=> 'orange'));
square('q-fit-flat',voxels([36,165],46,grid(2,2,1),()=> 'orange'));
square('q-fit-row',voxels([18,160],40,grid(4,1,1),()=> 'orange'));

add('sample-build',620,350,
    box([150,285],90,[0,0,0,3.15,1.65,.48],'orange')+
    box([150,285],90,[.18,.24,.48,1,1,1],'aqua')+
    cylinder(374,217,47,100,'pine')+
    box([150,285],90,[.27,.35,1.48,.78,.78,.78],'blue'));

const practiceKnown = [...grid(3,1,1),[0,0,1]];
add('fit-practice',610,295,
    box([38,232],68,[0,0,0,3,1,2],'orange',true)+
    voxels([38,232],68,practiceKnown,()=> 'pine')+
    arrow(292,159,339,159)+
    voxels([365,232],64,grid(3,1,2),(x,y,z)=>z===1&&x>0?'orange':'pine'));

const links={
  'cylinder-stack-compare':['stack-aligned','stack-offset','stack-mismatch'],
  'life-shapes':['life-long-box','life-cube','life-cylinder','life-ball'],
  'lab-invitation':['lab-welcome','sample-build'],
  'sort-opening':['token-long','sample-long','sample-cube'],
  'stack-opening':['piece-thin','base-thin','base-wide'],
  'lab-problem':['lab-plan','fit-practice'],
  'home-example':['family-map','sample-long','sample-cylinder','sample-cube','sample-ball'],
};
for (const [name,inputs] of Object.entries(links)) {
  add(name,name==='home-example'?730:name==='life-shapes'?790:650,343,'',inputs);
}

async function render(key,{width,height,draw}) {
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'">'+
    '<rect width="100%" height="100%" fill="'+paper+'"/>'+draw+'</svg>';
  const inputs=art[key];
  const layers=[];
  for (const [index,name] of inputs.entries()) {
    const cover=key==='lab-invitation'||key==='lab-problem';
    const size=cover?285:key==='home-example'?(index===0?274:143):key==='life-shapes'?173:179;
    const left=cover?25+index*315:key==='home-example'?(index===0?26:328+((index-1)%2)*172):key==='life-shapes'?22+191*index:26+207*index;
    const top=cover?29:key==='home-example'?(index===0?34:15+Math.floor((index-1)/2)*157):81;
    const image=await sharp(file(name)).resize(size,size,{fit:'contain',background:paper}).png().toBuffer();
    layers.push({input:image,left,top});
  }
  await sharp(Buffer.from(svg)).composite(layers).png().toFile(file(key));
}

if (process.argv.includes('--describe')) {
  console.log(JSON.stringify({art,pieces,gapBoards,target,known,remainder}));
} else {
  for (const [key,value] of pictures) await render(key,value);
}

import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../../../../student-web/package.json', import.meta.url));
const sharp = require('sharp');
const asset = key => fileURLToPath(new URL('../assets/' + key + '.png', import.meta.url));
const cream = '#fcf1d6';
const ink = '#3c5140';
const accent = '#a24726';
const colors = {a:'#dba760', b:'#84a491', m:'#8fbac6', d:'#d8846c', e:'#bba75e', q:'#8b9bba', p:'#c48979'};
const art = {};
const pictures = new Map();
const part = (id, poly) => ({id, poly});
const rect = (x,y,w,h) => [[x,y],[x+w,y],[x+w,y+h],[x,y+h]];
const move = ({id,poly}, dx,dy) => part(id,poly.map(([x,y])=>[x+dx,y+dy]));
const transform = (entry, fn) => part(entry.id,entry.poly.map(fn));

// One small triangle has unit legs. Every image uses these seven physical shapes.
const canonical = {
  a:[[0,0],[2,0],[0,2]], b:[[0,0],[2,0],[0,2]],
  m:[[0,0],[2,0],[1,1]], d:[[0,0],[1,0],[0,1]], e:[[0,0],[1,0],[0,1]],
  q:rect(0,0,1,1), p:[[0,1],[1,1],[2,0],[1,0]],
};
const setLayout = {
  a:[[0,0],[4,0],[2,2]], b:[[0,0],[2,2],[0,4]], m:[[4,2],[4,4],[2,4]],
  d:[[4,0],[4,2],[3,1]], e:[[2,2],[3,3],[1,3]], q:[[3,1],[4,2],[3,3],[2,2]],
  p:[[1,3],[3,3],[2,4],[0,4]],
};
const unitBoard = Object.entries(setLayout).map(([id,polygon])=>part(id,polygon.map(([x,y])=>[(x+y)/2,(y-x)/2])));
const squareBoard = {outline:[[0,0],[2,-2],[4,0],[2,2]], parts:unitBoard};
const twoSmall = {outline:[[0,0],[2,0],[1,1]], parts:[
  part('d',[[0,0],[1,0],[1,1]]), part('e',[[1,0],[2,0],[1,1]]),
]};
const twoLarge = {outline:[[0,0],[4,0],[2,2]], parts:[
  part('a',[[0,0],[2,0],[2,2]]), part('b',[[2,0],[4,0],[2,2]]),
]};
const threeSquare = {outline:canonical.a, parts:[part('q',canonical.q),
  part('d',[[0,1],[0,2],[1,1]]), part('e',[[1,0],[2,0],[1,1]])]};
const threeMedium = {outline:canonical.a, parts:[part('m',canonical.m),
  part('d',[[0,0],[1,1],[0,1]]), part('e',[[0,1],[1,1],[0,2]])]};
const threeSlanted = {outline:canonical.a, parts:[part('p',canonical.p),
  part('d',[[0,0],[1,0],[0,1]]), part('e',[[0,1],[1,1],[0,2]])]};
const fourTriangle = {outline:twoLarge.outline, parts:[
  ...threeSquare.parts.map(entry=>transform(entry,([x,y])=>[2-y,x])),twoLarge.parts[1],
]};
const squarePair = {outline:rect(0,0,1,1), parts:[part('d',canonical.d),part('e',[[1,0],[1,1],[0,1]])]};
const rectanglePair = {outline:rect(0,0,2,1), parts:[...squarePair.parts,part('q',rect(1,0,1,1))]};
const wrongPair = [part('q',canonical.q),part('d',[[1,0],[2,0],[1,1]])];
const fourGap = [...fourTriangle.parts.slice(0,3),move(fourTriangle.parts[3],.34,0)];
const fourOverlap = [...fourTriangle.parts.slice(0,3),move(fourTriangle.parts[3],-.32,0)];
const house = [part('a',canonical.a),part('b',[[2,0],[2,2],[0,2]]),
  part('m',[[0,0],[2,0],[1,-1]]),part('q',rect(2,1,1,1)),
  part('d',[[0,0],[0,1],[-1,1]]),part('e',[[3,1],[4,2],[3,2]]),
  part('p',[[0,2],[1,2],[0,3],[-1,3]])];
const examples = {squareBoard,twoSmall,twoLarge,threeSquare,threeMedium,threeSlanted,fourTriangle,squarePair,rectanglePair};

const patches = {
  'large': {example:twoLarge, missing:1}, 'small': {example:twoSmall, missing:1},
  'square': {example:threeSquare, missing:0}, 'corner': {example:threeSquare, missing:2},
  'medium': {example:threeMedium, missing:0}, 'slant': {example:threeSlanted, missing:0},
  'added-large': {example:fourTriangle, missing:3, turn:true},
};

function register(key,width,height,content='',inputs=[]){
  art[key]=inputs;
  pictures.set(key,{width,height,content,inputs});
}
const map = (points,x,y,scale) => points.map(([u,v])=>[x+u*scale,y+v*scale]);
function polygon(points,fill,stroke=ink,width=3,extra=''){
  return '<polygon points="'+points.map(p=>p.map(n=>Number(n.toFixed(3))).join(',')).join(' ')+
    '" fill="'+fill+'" stroke="'+stroke+'" stroke-width="'+width+'" stroke-linejoin="round" '+extra+'/>';
}
function tiles(entries,x,y,scale,{selected,soft=false,width=3}={}){
  return entries.map(({id,poly})=>polygon(map(poly,x,y,scale),selected&&!selected.includes(id)?'#e6dbc1':colors[id],
    selected&&!selected.includes(id)?'#a79d85':ink,width,soft?'fill-opacity=".72"':'')).join('');
}
function perimeter(poly,x,y,scale,stroke=accent,width=5,dashed=false){
  return polygon(map(poly,x,y,scale),'none',stroke,width,dashed?'stroke-dasharray="7 5"':'');
}
const arrow = (x,y,xx,yy) => {
  const a=Math.atan2(yy-y,xx-x), ends=[a+.5,a-.5].map(v=>[xx-15*Math.cos(v),yy-15*Math.sin(v)]);
  return '<path d="M'+x+' '+y+'L'+xx+' '+yy+'" stroke="'+accent+'" stroke-width="4" stroke-linecap="round"/>'+
    polygon([[xx,yy],...ends],accent,accent,1);
};
function centered(entries,width,height,scale,params){
  const x=entries.flatMap(t=>t.poly.map(p=>p[0])),y=entries.flatMap(t=>t.poly.map(p=>p[1]));
  const dx=width/2-(Math.min(...x)+Math.max(...x))*scale/2;
  const dy=height/2-(Math.min(...y)+Math.max(...y))*scale/2;
  return tiles(entries,dx,dy,scale,params);
}
const rotate = ([x,y]) => [-y,x];
const rotateExample = example => ({outline:example.outline.map(rotate),parts:example.parts.map(t=>transform(t,rotate))});
const inventory = [move(part('a',canonical.a),0,0),move(part('b',canonical.b),2.48,0),
  move(part('m',canonical.m),4.9,0),move(part('d',canonical.d),7.3,0),move(part('e',canonical.e),8.68,0),
  move(part('q',canonical.q),4.9,1.6),move(part('p',canonical.p),6.65,1.6)];
const rotatedSet=Object.entries(setLayout).map(([id,poly])=>part(id,poly.map(([x,y])=>[4-y,x])));

register('opening-scene',680,332,'',['gallery-entrance','exhibition-kids']);
register('one-complete-set',600,320,tiles(rotatedSet,178,40,61));
register('seven-loose-pieces',680,307,centered(inventory,680,307,61));
register('two-will-fit',690,330,
  tiles([part('a',[[0,0],[2,0],[2,2]]),part('b',[[3.6,0],[5.6,0],[5.6,2]])],22,103,56)+
  arrow(355,158,400,158)+tiles(twoLarge.parts,416,103,56));
register('two-try-again',640,320,tiles(wrongPair,41,90,105)+
  arrow(288,138,354,138)+tiles(twoSmall.parts,389,105,105)+perimeter(twoSmall.outline,389,105,105));
register('three-with-square',640,330,tiles(threeSquare.parts,185,50,126)+perimeter(threeSquare.outline,185,50,126));
register('three-with-medium',640,330,tiles(threeMedium.parts,185,50,126)+perimeter(threeMedium.outline,185,50,126));
register('three-with-slanted',640,330,tiles(threeSlanted.parts,185,50,126)+perimeter(threeSlanted.outline,185,50,126));
register('four-big-outline',660,338,tiles(fourTriangle.parts,90,54,120)+perimeter(fourTriangle.outline,90,54,120));
register('three-or-four',690,320,tiles(threeSquare.parts,79,82,70)+arrow(262,151,341,151)+
  tiles(fourTriangle.parts,367,82,70)+perimeter(fourTriangle.outline,367,82,70));
register('square-to-rectangle',680,322,tiles(squarePair.parts,65,98,132)+
  arrow(222,158,288,158)+tiles(rectanglePair.parts,337,98,132)+perimeter(rectanglePair.outline,337,98,132));
register('house-exhibit',670,360,centered(house,670,360,78));
register('family-exhibit',670,330,'',['family-panel']);

for(const [key,{example,missing,turn}] of Object.entries(patches)){
  const {outline,parts}=turn?rotateExample(example):example;
  const piece=parts[missing], given=parts.filter((_,i)=>i!==missing), scale=40;
  const minX=Math.min(...outline.map(p=>p[0])),minY=Math.min(...outline.map(p=>p[1]));
  const maxX=Math.max(...outline.map(p=>p[0])),maxY=Math.max(...outline.map(p=>p[1]));
  const x=110-(minX+maxX)*scale/2,y=96-(minY+maxY)*scale/2;
  register('loose-'+key,220,192,centered([piece],220,192,scale,{width:4}));
  register('target-'+key,220,192,tiles(given,x,y,scale,{width:4})+
    perimeter(outline,x,y,scale,accent,5,true)+perimeter(piece.poly,x,y,scale,accent,5,true));
  register('finished-'+key,220,192,tiles(parts,x,y,scale,{width:4})+perimeter(outline,x,y,scale,ink,5));
}
register('marble-intro',640,335,'',['loose-large','target-large','target-small']);

const snakeCards = {
  'r-tri': {outline:twoSmall.outline, scale:55},
  't-small': {parts:twoSmall.parts,scale:55},
  't-big': {parts:twoLarge.parts,scale:27.5},
  't-three-q': {parts:threeSquare.parts,scale:55},
  't-three-p': {parts:rotateExample(threeSlanted).parts,scale:55},
  't-four': {parts:fourTriangle.parts,scale:27.5},
  'off-square': {parts:squarePair.parts,scale:84},
  'off-gap': {parts:fourGap,scale:25},
  'off-angled': {parts:wrongPair,scale:55},
  'r-rect': {outline:rectanglePair.outline,scale:55},
  'rect-flat': {parts:rectanglePair.parts,scale:55},
  'rect-high': {parts:rotateExample(rectanglePair).parts,scale:44},
  'off-shift': {parts:[...squarePair.parts,move(rectanglePair.parts[2],0,.31)],scale:50},
};
for(const [key,{parts,outline,scale}] of Object.entries(snakeCards)){
  register('snake-'+key,132,112,parts?centered(parts,132,112,scale,{width:5}):
    polygon(map(outline,11,32,scale),'#e2b789',ink,6));
}
register('snake-intro',640,335,'',['snake-r-tri','snake-t-three-q','snake-off-square']);

const quiz = (key,parts,scale,opts={}) => register(key,255,239,centered(parts,255,239,scale,opts));
const quizInventory = [move(part('a',canonical.a),0,0),move(part('b',canonical.b),2.2,0),
  move(part('m',canonical.m),4.4,0),move(part('d',canonical.d),0,2.4),move(part('e',canonical.e),1.35,2.4),
  move(part('q',canonical.q),2.8,2.4),move(part('p',canonical.p),4.3,2.4)];
quiz('q-inventory-wrong-square',quizInventory,35,{selected:['a','b','d','e','q']});
quiz('q-inventory-five-triangles',quizInventory,35,{selected:['a','b','m','d','e']});
quiz('q-inventory-extra-board',quizInventory,35,{selected:['a','b','m','d','e','p']});
const sideTriangle=rotateExample(twoSmall);
register('q-two-goal',255,239,perimeter(sideTriangle.outline,171,35,82,accent,6,true));
quiz('q-two-square',squarePair.parts,82);
quiz('q-two-angled',wrongPair,82);
quiz('q-two-triangle',sideTriangle.parts,82);
quiz('q-three-square',rotateExample(threeSquare).parts,84);
quiz('q-three-medium',rotateExample(threeMedium).parts,84);
quiz('q-three-slanted',rotateExample(threeSlanted).parts,84);
quiz('q-four-gapped',fourGap,49);
quiz('q-four-fitted',fourTriangle.parts,49);
quiz('q-four-overlap',fourOverlap,49,{soft:true});
quiz('q-make-square',squarePair.parts,113);
quiz('q-make-triangle',twoSmall.parts,93);
quiz('q-make-slide',[
  part('d',[[0,0],[1,0],[0,1]]),part('e',[[1,0],[1,1],[2,1]]),
],89);
quiz('q-rect-shifted',[...squarePair.parts,move(rectanglePair.parts[2],0,.26)],97);
quiz('q-rect-separated',[...squarePair.parts,move(rectanglePair.parts[2],.30,0)],97);
quiz('q-rect-complete',rotateExample(rectanglePair).parts,97);

async function render(key,{width,height,content,inputs}){
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'">'+
    '<rect width="100%" height="100%" fill="'+cream+'"/>'+content+'</svg>';
  const overlays=[];
  for(const [i,input] of inputs.entries()){
    const size=inputs.length===1?326:inputs.length===2?280:185;
    const x=inputs.length===1?Math.round((width-size)/2):inputs.length===2?40+i*320:25+i*203;
    const buffer=await sharp(asset(input)).resize(size,size,{fit:'contain',background:cream}).png().toBuffer();
    overlays.push({input:buffer,left:x,top:Math.round((height-size)/2)});
  }
  await sharp(Buffer.from(svg)).composite(overlays).png().toFile(asset(key));
}

if(process.argv.includes('--describe'))console.log(JSON.stringify({art,canonical,examples,patches,snakeCards,house,fourGap,fourOverlap}));
else for(const [key,picture] of pictures)await render(key,picture);

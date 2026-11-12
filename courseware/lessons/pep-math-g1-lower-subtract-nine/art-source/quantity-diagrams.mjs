import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const asset=key=>fileURLToPath(new URL('../assets/'+key+'.png',import.meta.url));
const paper='#fff2d5', pine='#284c3c', ochre='#a7472b', moss='#cbd7b1';
const images=new Map();
const definitions={};
const data={worked:14, tileTotals:[11,12,13,14,15], quizTotals:[16,17,18,19]};
const lamp='single-lantern', badge='festival-rosette';
const icon=Object.fromEntries(await Promise.all([lamp,badge].map(async key=>[key,
  'data:image/png;base64,'+(await sharp(asset(key)).resize(78,78,{fit:'inside'}).png().toBuffer()).toString('base64'),
])));

function register(key,width,height,svg,inputs=[],quantity=null){
  images.set(key,{width,height,svg,inputs});
  definitions[key]={inputs,quantity};
}
function rectangle(x,y,w,h,fill,stroke='none',sw=0,r=10){
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
}
const line=(x,y,xx,yy,color=pine,width=4)=>`<path d="M${x} ${y}L${xx} ${yy}" stroke="${color}" stroke-width="${width}" stroke-linecap="round"/>`;
function label(text,x,y,size,color=pine){
  return `<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="central" font-family="sans-serif" font-weight="700" font-size="${size}" fill="${color}">${text}</text>`;
}
const circle=(x,y,r,fill,stroke=pine,sw=2)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
function arrow(x,y,xx,yy){
  const angle=Math.atan2(yy-y,xx-x);
  return line(x,y,xx,yy,ochre,5)+[-.55,.55].map(d=>line(xx,yy,xx-16*Math.cos(angle+d),yy-16*Math.sin(angle+d),ochre,5)).join('');
}

function object(kind,x,y,size){
  if(icon[kind])return `<image href="${icon[kind]}" x="${x-size/2}" y="${y-size/2}" width="${size}" height="${size}"/>`;
  if(kind==='peg')return rectangle(x-size*.32,y-size*.35,size*.64,size*.70,'#dca76d',pine,2,4);
  return circle(x,y,size*.30,kind==='counter2'?'#c57e58':'#608f76',pine,2);
}
function slots(count,x,y,pitch,columns=5){
  return Array.from({length:count},(_,i)=>[x+(i%columns)*pitch,y+Math.floor(i/columns)*pitch]);
}
function icons(kind,count,x,y,pitch,columns=5){
  return slots(count,x,y,pitch,columns).map(([cx,cy])=>object(kind,cx,cy,pitch*.81)).join('');
}
function cell(kind,x,y,pitch,taken,boxed=true){
  const pad=pitch*.47;
  let mark=boxed?rectangle(x-pad,y-pad,pad*2,pad*2,taken?'#eadac3':'#fbecd0','#8d9e76',Math.max(1,pitch*.035),pitch*.09):'';
  mark+=taken?`<g opacity=".27">${object(kind,x,y,pitch*.82)}</g>`:object(kind,x,y,pitch*.82);
  if(taken)mark+=line(x-pitch*.32,y+pitch*.31,x+pitch*.32,y-pitch*.31,ochre,Math.max(2,pitch*.07));
  return mark;
}

function state(total,takenTray=0,takenLoose=0){
  const loose=total-10;
  if(!Number.isInteger(total)||total<10||total>19||takenTray<0||takenTray>10||takenLoose<0||takenLoose>loose){
    throw new Error('Invalid subtraction diagram');
  }
  return {total,tray:10,loose,takenTray,takenLoose,taken:takenTray+takenLoose,left:total-takenTray-takenLoose};
}
function board(model,x,y,pitch,kind=lamp,{compact=false}={}){
  const a=slots(10,x,y,pitch);
  const b=slots(model.loose,compact?x:x+pitch*6.3,compact?y+pitch*2.48:y,pitch);
  const slab=rectangle(x-pitch*.57,y-pitch*.57,pitch*5.14,pitch*2.14,moss,pine,Math.max(2,pitch*.06),pitch*.17);
  return slab+a.map(([cx,cy],i)=>cell(kind,cx,cy,pitch,i<model.takenTray)).join('')+
    b.map(([cx,cy],i)=>cell(kind,cx,cy,pitch,i<model.takenLoose,false)).join('');
}
function bigBoard(key,model,expression,kind=lamp){
  register(key,680,325,board(model,77,97,52,kind)+label(expression,340,252,48),icon[kind]?[kind]:[],model);
}
const original=state(data.worked), broken=state(data.worked,9), first=state(data.worked,0,4), chain=state(data.worked,5,4);
bigBoard('fourteen-before',original,'10 + 4 = 14');
bigBoard('take-nine-from-ten',broken,'10 − 9 = 1');
bigBoard('take-loose-first',first,'14 − 4 = 10');
bigBoard('take-five-next',chain,'10 − 5 = 5');
register('bring-five-together',680,325,
  board(broken,77,97,52)+arrow(281,177,389,177)+label('1 + 4 = 5',340,252,48),[lamp],broken);
register('festival-opening',670,332,'',['festival-entrance','festival-kids']);
register('home-counting',670,332,'',['family-count','window-light']);

function joined(total,x,y,pitch,kind=lamp,need=false){
  const rest=total-9;
  const marks=slots(total,x,y,pitch,9);
  return rectangle(x-pitch*.57,y-pitch*.52,9.14*pitch,pitch*1.04,'#e7ad79','#95513b',3)+
    rectangle(x-pitch*.57,y+pitch*.49,(rest+.14)*pitch,pitch*1.04,'#bcd2a8',pine,3)+
    marks.map(([cx,cy],i)=>need&&i>=9?rectangle(cx-pitch*.36,cy-pitch*.36,pitch*.72,pitch*.72,'#f7ecd1',pine,2,3):
      cell(kind,cx,cy,pitch,false,false)).join('');
}
register('join-fourteen',680,325,joined(14,142,81,49)+label('9 + 5 = 14',340,237,48),[lamp],{total:14,packed:9,left:5});
register('compare-after-nine',680,325,
  [11,12,13].map((total,i)=>{
    const y=72+87*i;
    const remainder=total-9;
    return label(`${total} − 9`,105,y,42)+arrow(204,y,271,y)+
      rectangle(305,y-35,238,70,'#e5e6bc','#9b9e72',2)+icons(lamp,remainder,335,y,50,6)+label(remainder,603,y,42);
  }).join(''),[lamp],{totals:[11,12,13],taken:9,remainders:[2,3,4]});
register('why-one-extra',680,325,board(state(13,9),77,97,52)+label('1 + 3 = 4',340,250,48),[lamp],state(13,9));

register('which-work-remains',680,325,joined(12,142,80,49,'peg',true)+label('12 − 9 = 3',340,244,48),[],{total:12,finished:9,left:3});
register('start-with-the-whole',680,325,
  rectangle(58,41,275,131,'#e6c38f','#946a48',3)+icons('counter',6,97,79,54,4)+
  rectangle(368,41,254,131,'#bfcc9d',pine,3)+icons('counter2',7,404,79,54,4)+
  label('6 + 7 = 13',340,214,43)+label('13 − 9 = 4',340,274,43),[],{groups:[6,7],total:13,taken:9,left:4});
register('spaces-between',680,325,
  Array.from({length:10},(_,i)=>rectangle(75+i*59,119,20,65,'#bf7d54',pine,2,5)).join('')+
  Array.from({length:9},(_,i)=>circle(114+i*59,202,9,'#6c9a74')).join(''),[],{markers:10,spaces:9});

for(const total of data.tileTotals){
  const removal=state(total,9);
  const rest=total-9;
  register('tile-state-'+total,236,228,board(removal,42,38,37,lamp,{compact:true})+label(`${total}−9`,118,198,46),[lamp],removal);
  register('tile-left-'+rest,206,190,icons(lamp,rest,48,52,52,3)+label(rest,102,154,53),[lamp],{left:rest});
  register('delivery-total-'+total,226,200,
    rectangle(30,23,165,120,'#e7dcaa',pine,3)+icons(lamp,total,45,43,24,7)+label(total,113,166,48),[lamp],{total});
  register('delivery-job-'+total,234,228,joined(total,26,48,20,lamp,true)+label(total,118,134,56)+label('9 + ?',118,190,36),[lamp],{total,packed:9,unfilled:rest});
  register('delivery-proof-'+total,244,215,joined(total,32,50,20)+label(`9 + ${rest} = ${total}`,122,153,40),[lamp],{total,packed:9,left:rest});
}
register('tiles-ready',670,332,'',['tile-state-11','tile-left-2','tile-left-4']);
register('delivery-ready',670,332,'',['delivery-job-11','tile-left-2','delivery-total-11']);

function cardAmount(key,kind,count){
  register(key,260,225,icons(kind,count,57,54,48,4)+label(count,130,188,43),icon[kind]?[kind]:[],{count});
}
register('q-sixteen-start',550,260,board(state(16),64,93,40,badge)+label('16 − 9',275,213,40),[badge],state(16));
for(const [key,count] of [['q-sixteen-a',6],['q-sixteen-b',7],['q-sixteen-c',8]])cardAmount(key,badge,count);
register('q-seventeen-start',550,260,board(state(17,9),64,91,40,'counter')+label('17 − 9',275,215,40),[],state(17,9));
for(const [key,loose] of [['q-seventeen-a',6],['q-seventeen-b',8],['q-seventeen-c',7]]){
  register(key,270,225,circle(57,72,19,'#ce7a52')+line(92,72,114,72,pine,4)+line(103,61,103,83,pine,4)+
    icons('counter',loose,143,60,34,4)+label(`1 + ${loose}`,135,175,42),[],{trayRemainder:1,loose});
}
register('q-nineteen-start',550,260,board(state(19),64,91,40,'peg')+label('19 − 9',275,215,40),[],state(19));
for(const [key,ten,loose] of [['q-nineteen-a',0,9],['q-nineteen-b',1,9],['q-nineteen-c',0,8]]){
  const model=state(19,ten,loose);
  register(key,270,225,board(model,55,39,37,'peg',{compact:true})+label(model.left,239,190,36),[],model);
}
register('q-eighteen-total',550,244,joined(18,89,69,43,'counter')+label('18 − 9',275,191,40),[],{total:18,packed:9});
for(const [key,rest] of [['q-eighteen-a',8],['q-eighteen-b',9],['q-eighteen-c',10]]){
  register(key,275,224,
    icons('counter2',9,47,47,26,5)+icons('counter',rest,47,118,26,5)+label(`9 + ${rest}`,172,194,37),[],{first:9,second:rest,total:9+rest});
}
register('q-compare-totals',550,260,board(state(17),91,51,29,'counter')+
  board(state(18),91,155,29,'counter2')+label('17',38,65,33)+label('18',38,170,33)+
  label('−9',472,65,35)+label('−9',472,170,35),[],{totals:[17,18],take:9});
for(const [key,extra] of [['q-compare-a',1],['q-compare-b',0],['q-compare-c',2]]){
  register(key,270,225,icons('counter',8,49,36,32,5)+icons('counter2',8+extra,49,120,32,5)+
    label(extra===0?'8 = 8':`8 + ${extra}`,191,184,34),[],{referenceLeft:8,nextLeft:8+extra,extra});
}
register('q-display-slots',550,265,
  [10,9].map((count,i)=>{
    const x=64+255*i,y=69;
    return rectangle(x-20,y-22,210,100,i?'#e2ceaa':'#c9d4ac',pine,3)+
      slots(count,x,y,39,5).map(([cx,cy],j)=>rectangle(cx-13,cy-13,26,26,'#f2e2bf','#9f7d54',2,5)+
        (j<(i?4:5)?object('peg',cx,cy,25):'')).join('');
  }).join('')+label('10 + 9',275,201,46),[],{capacities:[10,9],placed:9,left:10});
for(const [key,count] of [['q-display-a',9],['q-display-b',11],['q-display-c',10]])cardAmount(key,'peg',count);

async function render(key,{width,height,svg,inputs}){
  const background='<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'">'+
    rectangle(0,0,width,height,paper,'none',0,0)+svg+'</svg>';
  const layers=[];
  if(!svg)for(const [i,input] of inputs.entries()){
    const size=inputs.length===2?287:184;
    const buffer=await sharp(asset(input)).resize(size,size,{fit:'contain',background:paper}).png().toBuffer();
    layers.push({input:buffer,left:34+i*(inputs.length===2?317:210),top:Math.floor((height-size)/2)});
  }
  await sharp(Buffer.from(background)).composite(layers).png().toFile(asset(key));
}

if(process.argv.includes('--describe'))console.log(JSON.stringify({definitions,data}));
else for(const [key,picture] of images)await render(key,picture);

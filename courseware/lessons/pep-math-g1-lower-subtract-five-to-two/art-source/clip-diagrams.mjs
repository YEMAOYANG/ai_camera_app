import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const asset=key=>fileURLToPath(new URL('../assets/'+key+'.png',import.meta.url));
const paper='#fff2d5', pine='#284c3c', ochre='#a7472b', moss='#cbd7b1';
const images=new Map();
const definitions={};
const data={worked:[12,5],marble:[[11,[2,3,4]],[12,[3,4,5]],[13,[4,5]]],
  tiles:[[11,2],[11,3],[11,4],[12,3],[12,4],[12,5],[13,4],[13,5]]};
const clip='single-clip';
const kinds=[clip,'paper-flower','paper-boat','kraft-tag','round-biscuit','wax-crayon','seedling'];
const icon=Object.fromEntries(await Promise.all(kinds.map(async key=>[key,
  'data:image/png;base64,'+(await sharp(asset(key)).resize(72,72,{fit:'inside'}).png().toBuffer()).toString('base64'),
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
function arrow(x,y,xx,yy){
  const angle=Math.atan2(yy-y,xx-x);
  return line(x,y,xx,yy,ochre,5)+[-.55,.55].map(d=>line(xx,yy,xx-16*Math.cos(angle+d),yy-16*Math.sin(angle+d),ochre,5)).join('');
}

function object(kind,x,y,size){
  return `<image href="${icon[kind]}" x="${x-size/2}" y="${y-size/2}" width="${size}" height="${size}"/>`;
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
function board(model,x,y,pitch,kind=clip,{compact=false}={}){
  const a=slots(10,x,y,pitch);
  const b=slots(model.loose,compact?x:x+pitch*6.3,compact?y+pitch*2.48:y,pitch);
  const slab=rectangle(x-pitch*.57,y-pitch*.57,pitch*5.14,pitch*2.14,moss,pine,Math.max(2,pitch*.06),pitch*.17);
  return slab+a.map(([cx,cy],i)=>cell(kind,cx,cy,pitch,i>=model.tray-model.takenTray)).join('')+
    b.map(([cx,cy],i)=>cell(kind,cx,cy,pitch,i>=model.loose-model.takenLoose,false)).join('');
}
function bigBoard(key,model,expression,kind=clip){
  register(key,680,325,board(model,77,97,52,kind)+label(expression,340,252,48),icon[kind]?[kind]:[],model);
}
const before=state(12), breakFive=state(12,5), looseFirst=state(12,0,2), chain=state(12,3,2);
const takeTwo=state(11,2), takeTwoInSteps=state(11,1,1);
bigBoard('twelve-before',before,'10 + 2 = 12');
bigBoard('five-from-ten',breakFive,'10 − 5 = 5');
bigBoard('keep-seven',breakFive,'5 + 2 = 7');
bigBoard('first-take-two',looseFirst,'12 − 2 = 10');
bigBoard('then-take-three',chain,'10 − 3 = 7');
bigBoard('break-for-two',takeTwo,'8 + 1 = 9');
bigBoard('chain-for-two',takeTwoInSteps,'11 − 1 − 1 = 9');

register('craft-opening',670,332,'',['craft-entrance','clip-kids']);
register('craft-at-home',670,332,'',['family-craft','paper-textiles']);

function tailState(total,taken){
  const takenLoose=Math.min(total-10,taken);
  return state(total,taken-takenLoose,takenLoose);
}
function grouped(total,taken,x,y,pitch,kind=clip){
  const rest=total-taken;
  return rectangle(x-pitch*.53,y-pitch*.51,(taken+.08)*pitch,pitch*1.02,'#ebbd90','#a8724b',2)+
    rectangle(x-pitch*.53,y+pitch*.76,(rest+.08)*pitch,pitch*1.02,'#c4d3aa',pine,2)+
    icons(kind,taken,x,y,pitch,taken)+icons(kind,rest,x,y+pitch*1.27,pitch,rest);
}
register('put-five-back',680,320,grouped(12,5,91,77,67)+label('5 + 7 = 12',340,259,46),[clip],{total:12,taken:5,left:7});
register('four-seven-family',680,320,grouped(11,4,91,64,61)+
  label('4 + 7 = 11',340,202,41)+label('11 − 4 = 7',181,269,37)+label('11 − 7 = 4',497,269,37),[clip],
  {total:11,taken:4,left:7,converseTaken:7,converseLeft:4});

function comparison(key,examples,kind=clip){
  const rows=examples.map(([total,taken],i)=>{
    const y=64+91*i,x=194,pitch=29;
    const amount=rectangle(x-pitch*.5,y-25,pitch*total,50,'#d6dfb5','#83936c',2);
    const marks=slots(total,x,y,pitch,total).map(([cx,cy],j)=>cell(kind,cx,cy,pitch,j>=total-taken,false)).join('');
    return label(total+' − '+taken,84,y,42)+amount+marks+label(total-taken,630,y,42);
  }).join('');
  register(key,680,325,rows,icon[kind]?[kind]:[],{examples:examples.map(([total,taken])=>({total,taken,left:total-taken}))});
}
comparison('same-three',[[11,3],[12,3],[13,3]]);
comparison('same-twelve',[[12,3],[12,4],[12,5]]);
comparison('same-eleven',[[11,2],[11,3],[11,4]]);
comparison('all-nine',[[11,2],[12,3],[13,4]]);
bigBoard('three-from-units',state(13,0,3),'13 − 3 = 10');
register('equal-symbols',680,320,
  icons(clip,9,87,92,43,9)+label('11 − 2 = 12 − 3',340,186,47)+label('12 − 3 = 13 − 4',340,254,47),[clip],{equalLeft:9});

function quantityCard(key,kind,count){
  register(key,242,212,icons(kind,count,41,44,39,5)+label(count,121,180,48),icon[kind]?[kind]:[],{count});
}
for(const n of [2,3,4,5,7,8,9,10])quantityCard('clip-amount-'+n,clip,n);
for(const [total,queue] of data.marble){
  const original=state(total);
  register('marble-total-'+total,250,220,board(original,40,40,36,clip,{compact:true})+label(total,125,187,52),[clip],original);
  for(const take of queue){
    register('joined-'+total+'-'+take,245,204,grouped(total,take,27,53,20)+label(take+' + '+(total-take)+' = '+total,123,145,41),
      [clip],{total,taken:take,left:total-take});
  }
}
for(const [total,taken] of data.tiles){
  const model=tailState(total,taken);
  register('clip-card-'+total+'-'+taken,238,226,board(model,43,40,37,clip,{compact:true})+
    label(total+'−'+taken,119,194,46),[clip],model);
}
register('aim-ready',670,332,'',['marble-total-11','clip-amount-2','clip-amount-9']);
register('pair-ready',670,332,'',['clip-card-12-3','clip-card-11-2','clip-amount-9']);

function quizBoard(key,total,take,kind){
  const start=state(total);
  register(key,570,264,board(start,64,89,41,kind)+label(total+' − '+take,285,214,48),[kind],{total,taken:take,left:total-take});
}
quizBoard('q-flower-prompt',14,5,'paper-flower');
for(const [key,count] of [['a',8],['b',9],['c',10]])quantityCard('q-flower-'+key,'paper-flower',count);
register('q-tag-prompt',565,260,board(state(11),64,89,41,'kraft-tag')+
  label('5 + ? = 11',283,210,49),['kraft-tag'],{total:11,taken:5,left:6});
for(const [key,count] of [['a',6],['b',5],['c',7]])quantityCard('q-tag-'+key,'kraft-tag',count);
function pairedResult(key,kind,left,right){
  register(key,278,228,rectangle(14,15,120,157,'#e9cc9b',pine,2)+rectangle(145,15,120,157,'#d5dfb6',pine,2)+
    icons(kind,left,32,47,27,4)+icons(kind,right,163,47,27,4)+
    label(left,74,200,37)+label(right,205,200,37),[kind],{left,right});
}
function pairedTasks(key,kind,left,right){
  const columns=[left,right].map(([total,taken],i)=>{
    const x=38+i*279,y=66,pitch=33;
    return rectangle(x-pitch*.58,y-pitch*.56,227,131,i?'#d0dab1':'#e7c69a',pine,2)+
      icons(kind,total,x,y,pitch,6)+label(total+' − '+taken,x+90,219,42);
  }).join('');
  register(key,568,270,columns,[kind],{tasks:[left,right]});
}
pairedTasks('q-boat-prompt','paper-boat',[14,4],[15,4]);
for(const [key,left,right] of [['a',10,10],['b',11,10],['c',10,11]])pairedResult('q-boat-'+key,'paper-boat',left,right);
register('q-biscuit-prompt',565,257,rectangle(45,40,241,152,'#e9c993',pine,2)+
  icons('round-biscuit',6,85,83,49,4)+arrow(304,119,368,119)+label('?',442,121,78),
  ['round-biscuit'],{knownLeft:6,extraBefore:1,sameRemoved:true});
for(const [key,count] of [['a',6],['b',7],['c',8]])quantityCard('q-biscuit-'+key,'round-biscuit',count);
pairedTasks('q-crayon-prompt','wax-crayon',[16,3],[16,4]);
for(const [key,left,right] of [['a',12,13],['b',13,13],['c',13,12]])pairedResult('q-crayon-'+key,'wax-crayon',left,right);
function seedCard(key,total,taken,stem=false){
  const model=tailState(total,taken);
  register(key,stem?558:253,235,board(model,stem?65:48,42,stem?40:35,'seedling',{compact:!stem})+
    label(total+' − '+taken,stem?279:126,193,42),['seedling'],model);
}
seedCard('q-seed-prompt',16,5,true);
seedCard('q-seed-a',15,4);
seedCard('q-seed-b',15,5);
seedCard('q-seed-c',16,4);

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

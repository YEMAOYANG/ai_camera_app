import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const asset=key=>fileURLToPath(new URL('../assets/'+key+'.png',import.meta.url));
const paper='#fff2d5', pine='#284c3c', ochre='#a7472b', moss='#cbd7b1';
const images=new Map();
const definitions={};
const bookmark='single-bookmark',plant='one-potted-plant',scissors='one-scissors';
const kinds=[bookmark,plant,scissors];
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
const circle=(x,y,r,fill,stroke=pine,sw=2)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
function arrow(x,y,xx,yy){
  const angle=Math.atan2(yy-y,xx-x);
  return line(x,y,xx,yy,ochre,5)+[-.55,.55].map(d=>line(xx,yy,xx-16*Math.cos(angle+d),yy-16*Math.sin(angle+d),ochre,5)).join('');
}

function object(kind,x,y,size){
  return '<image href="'+icon[kind]+'" x="'+(x-size/2)+'" y="'+(y-size/2)+'" width="'+size+'" height="'+size+'"/>';
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
function board(model,x,y,pitch,kind=bookmark,{compact=false}={}){
  const a=slots(10,x,y,pitch);
  const b=slots(model.loose,compact?x:x+pitch*6.3,compact?y+pitch*2.48:y,pitch);
  const slab=rectangle(x-pitch*.57,y-pitch*.57,pitch*5.14,pitch*2.14,moss,pine,Math.max(2,pitch*.06),pitch*.17);
  return slab+a.map(([cx,cy],i)=>cell(kind,cx,cy,pitch,i<model.takenTray)).join('')+
    b.map(([cx,cy],i)=>cell(kind,cx,cy,pitch,i<model.takenLoose,false)).join('');
}
function bigBoard(key,model,expression,kind=bookmark){
  register(key,680,325,board(model,77,97,52,kind)+label(expression,340,252,48),icon[kind]?[kind]:[],model);
}
const table=Array.from({length:9},(_,i)=>Array.from({length:9-i},(_,j)=>[10+i,9-j]));
const expression=([n,k])=>n+'−'+k;
const methods={original:state(14),breakTen:state(14,8),toTen:state(14,0,4),chain:state(14,4,4)};
bigBoard('fourteen-on-table',methods.original,'10 + 4 = 14');
bigBoard('break-eight',methods.breakTen,'10 − 8 = 2　　2 + 4 = 6');
bigBoard('chain-eight',methods.chain,'14 − 4 = 10　　10 − 4 = 6');
register('library-opening',670,332,'',['reading-entrance','reading-kids']);
register('home-story',670,332,'',['family-story']);
register('greenhouse-context',670,332,'',['greenhouse-window']);

function fullTable(key,blank){
  const x=27,y=31,width=98,height=42;
  const cells=table.map((row,i)=>row.map((pair,j)=>{
    const left=x+j*width,top=y+i*height;
    const target=i===2&&j===3;
    return rectangle(left,top,width-2,height-2,target?'#eeb985':i%2?'#d6e1b8':'#e4e6c5','#5a7659',2,4)+
      label(blank&&target?'?':expression(pair),left+width/2,top+height/2,34);
  }).join('')).join('');
  register(key,942,438,cells,[],{cells:45,missing:blank?[12,6]:null,entries:table});
}
fullTable('table-one-gap',true);
fullTable('table-all-45',false);

function strip(key,rows,mode){
  const marks=rows.map(([n,k],i)=>{
    const rest=n-k,x=196,y=65+i*88,pitch=26;
    return label(n+' − '+k,100,y,38)+rectangle(x-pitch/2,y-25,n*pitch,49,'#dce2ba','#89a07b',2)+
      slots(n,x,y,pitch,n).map(([cx,cy],j)=>cell(bookmark,cx,cy,pitch,j>=rest,false)).join('')+
      label(rest,641,y,43);
  }).join('');
  register(key,690,325,marks,[bookmark],{mode,rows:rows.map(([n,k])=>[n,k,n-k])});
}
strip('same-column',[[12,9],[13,9],[14,9]],'column');
strip('same-row',[[12,9],[12,8],[12,7]],'row');
strip('same-diagonal',[[13,6],[14,7],[15,8]],'same-difference');
register('diagonal-arrows',680,325,
  rectangle(443,40,180,68,'#e5bd88',pine,3)+label('13−6',533,74,45)+
  rectangle(253,128,180,68,'#e5bd88',pine,3)+label('14−7',343,162,45)+
  rectangle(63,216,180,68,'#e5bd88',pine,3)+label('15−8',153,250,45)+
  arrow(452,102,417,129)+arrow(262,190,227,217),[],{moves:'lower-left',sameResult:7});

function partBar(total,known,kind,x,y,pitch,empty=false){
  const rest=total-known;
  const span=(count,fill,px)=>rectangle(px-pitch*.54,y-pitch*.55,(count+.08)*pitch,pitch*1.1,fill,pine,2,8);
  const right=x+known*pitch+12;
  return span(known,'#eac296',x)+span(rest,'#d6e0b8',right)+icons(kind,known,x,y,pitch,known)+
    (empty?slots(rest,right,y,pitch,rest).map(([cx,cy])=>rectangle(cx-pitch*.35,cy-pitch*.36,pitch*.7,pitch*.72,'#f6eed5',pine,1.8,5)).join(''):
      icons(kind,rest,right,y,pitch,rest));
}
register('check-six',680,325,partBar(14,8,bookmark,49,108,41)+label('8 + 6 = 14',340,241,49),
  [bookmark],{total:14,known:8,left:6});
register('bookmark-missing',690,325,partBar(16,7,bookmark,51,82,36,true)+
  icons(scissors,3,105,179,40,3)+label('16 − 7 = 9',423,237,48),[bookmark,scissors],{total:16,known:7,irrelevant:3,left:9});
register('part-not-total',690,325,partBar(16,7,bookmark,51,110,36)+
  label('7 + 9 = 16',345,244,49),[bookmark],{total:16,known:7,left:9});
register('missing-eight',690,325,partBar(13,5,bookmark,56,98,44)+
  label('13 − ? = 5',345,243,52),[bookmark],{total:13,left:5,removed:8});
register('compare-fixed',690,325,partBar(13,5,bookmark,52,73,36)+partBar(13,6,bookmark,52,173,36)+
  label('13−5 > 13−6',344,271,49),[bookmark],{tasks:[[13,5],[13,6]],results:[8,7]});
register('compare-target-five',690,325,icons(bookmark,13,58,83,43,13)+icons(bookmark,8,58,160,43,13)+
  rectangle(58+7.5*43,56,43*5,52,'none',ochre,3,5)+label('13 − 8 = 5',345,256,48),
  [bookmark],{larger:13,smaller:8,difference:5});
register('two-operations',690,325,rectangle(47,37,259,95,'#e6c292',pine,2)+icons(bookmark,8,72,65,40,5)+
  rectangle(371,37,259,95,'#cad7b0',pine,2)+icons(bookmark,6,394,65,40,5)+label('+',342,85,50)+
  label('8 + 6 = 14',345,196,46)+label('14 − 7 = 7',345,268,46),[bookmark],{first:[8,6,14],second:[14,7,7]});

function person(x,y,scale,active=false){
  const color=active?ochre:pine;
  return circle(x,y-scale*.26,scale*.115,color,color,1)+rectangle(x-scale*.105,y-scale*.10,scale*.21,scale*.40,color,color,1,3)+
    line(x-scale*.07,y+scale*.22,x-scale*.08,y+scale*.47,color,Math.max(2,scale*.065))+
    line(x+scale*.07,y+scale*.22,x+scale*.08,y+scale*.47,color,Math.max(2,scale*.065));
}
function lineOfPeople(key,total,left,width=690,height=325){
  const pitch=(width-70)/(total-1);
  const marks=slots(total,35,101,pitch,total).map(([x,y],i)=>person(x,y,pitch*1.1,i===left)).join('');
  const middle=35+pitch*left,right=total-left-1;
  register(key,width,height,marks+
    line(24,153,middle-pitch*.5,153,pine,4)+label(left,(middle+16)/2,190,40)+
    label('1',middle,190,42,ochre)+line(middle+pitch*.5,153,width-26,153,pine,4)+
    label('?',(middle+width-22)/2,190,41)+label(total,width/2,height-28,38),[],{total,left,middle:1,right});
}
lineOfPeople('line-with-middle',14,6);
register('family-number-story',690,325,partBar(12,5,bookmark,70,111,42)+
  label('5 + 7 = 12',346,246,48),[bookmark],{total:12,parts:[5,7]});

const hops=[
 {mode:'column',start:[12,8],route:[[13,8],[14,8],[15,8]],distractors:[[13,7],[14,9]]},
 {mode:'row',start:[15,9],route:[[15,8],[15,7],[15,6]],distractors:[[14,8],[16,7]]},
 {mode:'same-difference',start:[11,2],route:[[12,3],[13,4],[14,5]],distractors:[[12,4],[14,7]]},
];
const hopPairs=[...new Map(hops.flatMap(l=>[l.start,...l.route,...l.distractors]).map(p=>[expression(p),p])).values()];
for(const p of hopPairs){
  const [n,k]=p;
  register('hop-'+n+'-'+k,176,88,label(expression(p),88,45,49),[],{n,k});
  if(hops.some(row=>row.route.some(([a,b])=>a===n&&b===k))){
    register('hop-proof-'+n+'-'+k,206,157,
      icons(bookmark,n-k,31,36,25,6)+label(n+'−'+k+'='+String(n-k),103,125,35),[bookmark],{n,k,left:n-k});
  }
}
for(const [name,x,y,xx,yy] of [['column',95,48,95,144],['row',50,99,147,99],['same-difference',148,53,55,146]]){
  register('rule-'+name,194,190,
    rectangle(26,24,142,142,'#d7dfb5',pine,3)+line(96,24,96,166,pine,2)+line(26,95,168,95,pine,2)+arrow(x,y,xx,yy),[],{mode:name});
}
register('hop-ready',670,332,'',['rule-column','hop-12-8','hop-13-8']);

const puzzles={
 'part-5':{kind:'part',total:11,known:6,result:5},'part-7':{kind:'part',total:13,known:6,result:7},
 'plus-6':{kind:'plus',total:15,known:9,result:6},'minus-14':{kind:'minus',taken:8,left:6,result:14},
 'needed-9':{kind:'ignore',total:16,known:7,irrelevant:3,result:9},
 'compare-7':{kind:'compare',larger:15,smaller:8,result:7},
 'steps-5':{kind:'steps',total:15,taken:8,extraTaken:2,result:5},
};
function puzzleArt(key,p){
  let picture,symbol;
  if(p.kind==='part'||p.kind==='ignore'){
    picture=partBar(p.total,p.known,bookmark,25,55,16,true);
    if(p.irrelevant)picture+=icons(scissors,p.irrelevant,50,107,24,3);
    symbol=p.total+'−'+p.known;
  }else if(p.kind==='plus'){
    picture=partBar(p.total,p.known,bookmark,25,55,17,true);
    symbol=p.known+'+?='+p.total;
  }else if(p.kind==='minus'){
    picture=partBar(p.result,p.taken,bookmark,25,55,17);
    symbol='?−'+p.taken+'='+p.left;
  }else if(p.kind==='compare'){
    picture=icons(bookmark,p.larger,25,31,18,8)+icons(bookmark,p.smaller,25,90,18,8);
    symbol=p.larger+'−'+p.smaller;
  }else{
    picture=board(state(p.total,p.taken),36,35,23,bookmark,{compact:true})+
      label('−'+p.extraTaken,224,113,35);
    symbol=p.total+'−'+p.taken+'−'+p.extraTaken;
  }
  register('crate-'+key,320,194,picture+label(symbol,160,160,38),p.irrelevant?[bookmark,scissors]:[bookmark],p);
}
for(const [key,p] of Object.entries(puzzles))puzzleArt(key,p);
for(const n of [5,6,7,9,14]){
  register('depot-amount-'+n,212,184,icons(bookmark,n,37,44,27,6)+label(n,106,149,52),[bookmark],{count:n});
}
register('depot-ready',670,332,'',['crate-part-5','depot-amount-5','depot-amount-7']);

register('q-borrow-stem',560,238,board(state(14),56,81,42,bookmark)+label('?',280,199,48),
  [bookmark],{total:14});
for(const [suffix,n,k] of [['a',14,6],['b',14,4],['c',14,2]]){
  const model=state(n);
  register('q-borrow-'+suffix,252,212,board(model,40,40,33,bookmark,{compact:true})+label(n+'−'+k,126,179,44),
    [bookmark],{n,k,needsTen:k>n-10});
}
for(const [key,n,k] of [['q-col-stem',16,8],['q-col-a',17,9],['q-col-b',17,8],['q-col-c',16,9],
                        ['q-diag-stem',11,5],['q-diag-a',10,5],['q-diag-b',10,4],['q-diag-c',10,3]]){
  register(key,245,214,rectangle(22,47,201,106,'#d8e1b9',pine,3)+label(n+'−'+k,122,102,58),[],{n,k,left:n-k});
}
register('q-row-stem',535,224,rectangle(46,58,175,96,'#d8e1b9',pine,3)+label('16−9',134,104,49)+
  arrow(236,107,305,107)+rectangle(323,58,160,96,'#e5cb9a',pine,3)+label('?',402,105,50),[],{start:[16,9],move:'right'});
for(const [key,delta] of [['q-row-a',-1],['q-row-b',0],['q-row-c',1]]){
  const n=7+delta;
  register(key,261,218,icons(bookmark,7,37,36,30,6)+icons(bookmark,n,37,110,30,6)+
    label(delta<0?'−1':delta===0?'=0':'+1',211,171,38),[bookmark],{before:7,after:n,delta});
}
register('q-plants-stem',700,264,partBar(17,8,plant,36,83,29,true)+icons(scissors,4,72,176,37,4)+
  label('17',452,190,55),[plant,scissors,'greenhouse-context'],{total:17,known:8,irrelevant:4,left:9});
for(const [key,n] of [['q-plants-a',4],['q-plants-b',5],['q-plants-c',9]]){
  register(key,255,221,icons(plant,n,45,59,37,5)+label(n,127,181,48),[plant],{count:n});
}
lineOfPeople('q-line-stem',16,7,570,250);
for(const [key,n] of [['q-line-a',8],['q-line-b',9],['q-line-c',7]]){
  register(key,260,215,slots(n,51,55,40,4).map(([x,y])=>person(x,y,34)).join('')+
    label(n,130,178,46),[],{count:n});
}

async function render(key,{width,height,svg,inputs}){
  const background='<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'">'+
    rectangle(0,0,width,height,paper,'none',0,0)+svg+'</svg>';
  const layers=[];
  if(key==='q-plants-stem'){
    const context=await sharp(asset('greenhouse-context')).resize(151,124,{fit:'cover'}).png().toBuffer();
    layers.push({input:context,left:540,top:105});
  }
  if(!svg)for(const [i,input] of inputs.entries()){
    const size=inputs.length===1?300:inputs.length===2?287:184;
    const buffer=await sharp(asset(input)).resize(size,size,{fit:'contain',background:paper}).png().toBuffer();
    layers.push({input:buffer,left:inputs.length===1?Math.floor((width-size)/2):34+i*(inputs.length===2?317:210),top:Math.floor((height-size)/2)});
  }
  await sharp(Buffer.from(background)).composite(layers).png().toFile(asset(key));
}

if(process.argv.includes('--describe'))console.log(JSON.stringify({definitions,table,hops,puzzles,methods}));
else for(const [key,picture] of images)await render(key,picture);

import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const file=key=>fileURLToPath(new URL('../assets/'+key+'.png',import.meta.url));
const art=new Map();
const pine='#264b41',mint='#d7e9da',warm='#fff1d5',gold='#f2c774',ink='#7e3d30',coral='#ae4b31';
export function digits(n){
  if(!Number.isInteger(n)||n<0||n>100)throw new RangeError('expected a quantity from 0 to 100');
  return [Math.floor(n/100),Math.floor(n/10)%10,n%10];
}
export function compare(a,b){
  const left=digits(a),right=digits(b);
  const place=left.findIndex((d,i)=>d!==right[i]);
  return {left:a,right:b,group:place<0?'eq':left[place]>right[place]?'gt':'lt',place:place<0?null:['hundreds','tens','ones'][place]};
}
const rect=(x,y,w,h,fill,stroke=pine,sw=2,r=9)=>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
const dot=(x,y,r,fill=ink)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}"/>`;
const line=(x,y,xx,yy,color=pine,width=5)=>
  `<path d="M${x} ${y}L${xx} ${yy}" stroke="${color}" stroke-width="${width}" stroke-linecap="round"/>`;
const text=(v,x,y,size,color=pine)=>
  `<text x="${x}" y="${y}" dominant-baseline="central" text-anchor="middle" font-family="Hiragino Sans GB, sans-serif" font-size="${size}" font-weight="700" fill="${color}">${v}</text>`;
const inset=(shape,x,y,w,h,vw,vh)=>
  `<svg x="${x}" y="${y}" width="${w}" height="${h}" viewBox="0 0 ${vw} ${vh}" preserveAspectRatio="none">${shape}</svg>`;
const panel=(w,h)=>rect(3,3,w-6,h-6,mint,pine,4,21);
function arrow(x,y,xx,yy,color=coral,width=7){
  const angle=Math.atan2(yy-y,xx-x),tip=3.3*width;
  return line(x,y,xx,yy,color,width)+[-.52,.52].map(d=>
    line(xx,yy,xx-tip*Math.cos(angle+d),yy-tip*Math.sin(angle+d),color,width)).join('');
}
function glyph(group,x,y,s,color=pine){
  if(group==='blank')return rect(x-s*.45,y-s*.43,s*.9,s*.86,'#fff9e8',pine,4,s*.12);
  const left=x-s*.36,right=x+s*.36,top=y-s*.30,bottom=y+s*.30,sw=s*.08;
  if(group==='eq')return line(left,y-s*.15,right,y-s*.15,color,sw)+line(left,y+s*.15,right,y+s*.15,color,sw);
  return group==='gt'?line(left,top,right,y,color,sw)+line(left,bottom,right,y,color,sw):
    line(right,top,left,y,color,sw)+line(right,bottom,left,y,color,sw);
}
function register(key,w,h,svg,proof=null){art.set(key,{w,h,svg,proof});}
function numberCard(n,w=184,h=114){
  return rect(4,4,w-8,h-8,warm,pine,4,14)+text(n,w/2,h*.52,h*.67);
}
function stamps(n,{label=true,linked=0,accent='none'}={}){
  const [hundreds,tens,ones]=digits(n);
  if(hundreds)throw new RangeError('use a three-place abacus for 100');
  const frame=rect(5,5,310,326,warm,pine,4,17);
  const top=label?text(n,160,32,37):'';
  const tenRows=Array.from({length:tens},(_,row)=>{
    const y=62+row*24, highlighted=accent==='tens'&&row>=linked;
    return rect(25,y-10,270,19,highlighted?gold:row<linked?'#d7ead8':'#f6dab3',highlighted?coral:pine,highlighted?3:1,6)+
      Array.from({length:10},(_,col)=>dot(38+27*col,y,6.5)).join('');
  }).join('');
  const singles=rect(25,282,270,28,accent==='ones'?gold:'#e7efe1',accent==='ones'?coral:pine,accent==='ones'?3:1,7)+
    Array.from({length:ones},(_,col)=>dot(38+27*col,296,6.5)).join('');
  return frame+top+tenRows+singles;
}
function stampPair(key,a,b,{label=true,accent='none',align=false,show='blank'}={}){
  const shared=align?Math.min(digits(a)[1],digits(b)[1]):0;
  register(key,720,396,panel(720,396)+
    inset(stamps(a,{label,linked:shared,accent}),22,32,304,320,320,336)+
    inset(stamps(b,{label,linked:shared,accent}),394,32,304,320,320,336)+glyph(show,360,194,55),
    {...compare(a,b),shared,show,label,accent});
}
function abacus(n,{count=2,accent='none'}={}){
  const places=['hundreds','tens','ones'].slice(-count);
  const names={hundreds:'百位',tens:'十位',ones:'个位'};
  return rect(5,5,292,330,warm,pine,4,16)+places.map((place,i)=>{
    const d=digits(n)[3-count+i],x=(i+.5)*300/count,y=238,width=300/count*.83;
    return line(x,44,x,y,pine,7)+
      Array.from({length:d},(_,j)=>`<ellipse cx="${x}" cy="${y-9-j*20}" rx="${width*.33}" ry="8.5" fill="#ce8353" stroke="${pine}" stroke-width="2"/>`).join('')+
      rect(x-width/2,245,width,40,accent===place?gold:mint,accent===place?coral:pine,accent===place?4:2,7)+
      text(names[place],x,266,25)+(place==='hundreds'&&d===0?'':text(d,x,310,35));
  }).join('');
}
function abacusPair(key,a,b,{count=2,accent='none',show='blank'}={}){
  register(key,720,385,panel(720,385)+
    inset(abacus(a,{count,accent}),30,16,286,346,300,340)+
    inset(abacus(b,{count,accent}),404,16,286,346,300,340)+glyph(show,360,190,64),
    {...compare(a,b),count,accent,show});
}
function equation(key,a,b,show=compare(a,b).group){
  register(key,570,185,panel(570,185)+inset(numberCard(a),20,27,183,125,184,114)+
    glyph(show,285,91,96)+inset(numberCard(b),367,27,183,125,184,114),{...compare(a,b),show});
}
function tickLine(key,from,to,active,exclusive=false){
  const x=n=>64+(n-from)*578/(to-from);
  register(key,720,350,panel(720,350)+arrow(53,175,677,175,pine,6)+
    Array.from({length:to-from+1},(_,i)=>{
      const n=from+i,marked=active.includes(n);
      const y=marked?105:225;
      const m=exclusive&&(n===from||n===to)?'#fff9ea':marked?gold:warm;
      return line(x(n),161,x(n),190,pine,4)+rect(x(n)-33,y-25,66,49,m,marked?coral:pine,marked?4:2,8)+text(n,x(n),y,32);
    }).join('')+(active.length>1?arrow(x(active[0]),278,x(active.at(-1)),278,coral,5):''),
    {from,to,active,exclusive});
}
function order(key,values,{answer=false}={}){
  register(key,660,185,panel(660,185)+values.map((n,i)=>inset(numberCard(n),24+214*i,42,177,103,184,114)).join('')+
    (answer?arrow(93,157,568,157,coral,5):''),{values,descending:values.every((n,i)=>i===0||values[i-1]>n)});
}
function missing(key,left,right,group){
  register(key,585,185,panel(585,185)+text(left,139,91,92)+glyph(group,292,91,96)+text(right,447,91,92),
    {left,right,group});
}
stampPair('opening-26-12',26,12,{label:false});
stampPair('opening-51-47',51,47,{label:false});
stampPair('grouped-51-47',51,47,{accent:'tens',align:true,show:'gt'});
abacusPair('abacus-51-47',51,47,{accent:'tens',show:'gt'});
stampPair('grouped-71-75',71,75,{accent:'ones',align:true,show:'lt'});
abacusPair('abacus-71-75',71,75,{accent:'ones',show:'lt'});
equation('reverse-75-71',75,71);
stampPair('equal-64-64',64,64,{align:true,show:'eq'});
stampPair('one-vs-two-8-15',8,15,{show:'lt'});
abacusPair('boundary-97-100',97,100,{count:3,accent:'hundreds',show:'lt'});
tickLine('number-line-59-60',57,62,[59,60]);
abacusPair('abacus-59-60',59,60,{accent:'tens',show:'lt'});
abacusPair('swap-82-28',82,28,{accent:'tens',show:'gt'});
order('ordered-69-65-27',[69,65,27],{answer:true});
missing('open-tens-choice','□4',34,'gt');
order('try-tens-digits',[24,34,44]);
tickLine('between-10-and-14',10,14,[11,12,13],true);
register('range-10-14',620,185,panel(620,185)+text(10,95,92,75)+glyph('lt',206,92,74)+
  glyph('blank',310,92,88)+glyph('lt',414,92,74)+text(14,525,92,75),{low:10,high:14,exclusive:true});
missing('family-card-gap','□','□','blank');

export const snakePlans=[
  {start:46,steps:[['gt',54,39]]},
  {start:62,steps:[['lt',58,69],['eq',58,56]]},
  {start:76,steps:[['gt',79,74],['lt',73,81],['eq',73,70]]},
];
for(const n of new Set(snakePlans.flatMap(row=>[row.start,...row.steps.flatMap(([,yes,no])=>[yes,no])]))){
  register('snake-'+n,184,114,numberCard(n),{n});
}
for(const [i,{start,steps}] of snakePlans.entries()){
  let prev=start;
  for(const [j,[group,n]] of steps.entries()){
    equation('snake-proof-'+(i+1)+'-'+(j+1),n,prev,group);
    prev=n;
  }
}
for(const group of ['gt','lt','eq']){
  register('sign-'+group,110,103,rect(4,4,102,95,warm,pine,4,13)+glyph(group,55,51,85),{group});
}
register('empty-token',110,103,glyph('blank',55,51,90));
equation('snake-ready',54,46,'blank');

export const depotPairs=[[[32,45],[70,68]],[[84,84],[21,12],[55,56]],[[66,66],[98,92],[38,43],[89,93]]];
for(const [a,b] of depotPairs.flat()){
  equation('crate-'+a+'-'+b,a,b,'blank');
  equation('depot-proof-'+a+'-'+b,a,b);
  stampPair('depot-view-'+a+'-'+b,a,b,{label:true});
}
equation('depot-ready',32,45,'blank');

stampPair('q-stamp-stem',57,61,{label:false});
stampPair('q-magnet-stem',37,30,{label:false});
for(const [key,n] of [['q-stamps-a',57],['q-stamps-b',61],['q-magnets-a',37],['q-magnets-b',30]]){
  register(key,320,336,stamps(n,{label:false}),{n});
}
stampPair('q-equal-stem',26,26,{label:false});
equation('q-direction-stem',17,22,'blank');
order('q-order-stem',[19,36,33]);
order('q-order-a',[36,33,19],{answer:true});
order('q-order-b',[19,33,36],{answer:true});
order('q-order-c',[33,36,19],{answer:true});
missing('q-ones-stem',86,'8□','lt');
for(const n of [1,3,9])register('q-digit-'+n,184,114,numberCard(n),{n});

export const definitions=Object.fromEntries([...art].map(([key,{proof}])=>[key,proof]));
if(process.argv.includes('--describe'))console.log(JSON.stringify(definitions));
else if(process.argv[1]===fileURLToPath(import.meta.url)){
  await mkdir(fileURLToPath(new URL('../assets/',import.meta.url)),{recursive:true});
  for(const [key,{w,h,svg}] of art){
    const source=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${svg}</svg>`;
    await sharp(Buffer.from(source)).png({compressionLevel:9}).toFile(file(key));
  }
}

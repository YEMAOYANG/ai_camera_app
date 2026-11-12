import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const target=key=>fileURLToPath(new URL('../assets/'+key+'.png',import.meta.url));
const art=new Map();
const ink='#23473d',teal='#187362',warm='#fff0d3',mint='#d5e9dd',gold='#f2c577',coral='#a2472e';
export function arrangement(tens,ones){
  if(![tens,ones].every(n=>Number.isInteger(n)&&n>=0&&n<=9))throw new RangeError('each place holds zero to nine discs');
  return {tens,ones,discs:tens+ones,value:10*tens+ones};
}
export function arrangements(discs){
  if(!Number.isInteger(discs)||discs<0||discs>18)throw new RangeError('two places hold up to eighteen discs');
  const first=Math.max(0,discs-9),last=Math.min(9,discs);
  return Array.from({length:last-first+1},(_,i)=>arrangement(first+i,discs-first-i));
}
const box=(x,y,w,h,fill,stroke=ink,sw=3,r=12)=>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
const line=(x,y,xx,yy,color=coral,width=6)=>
  `<path d="M${x} ${y}L${xx} ${yy}" stroke="${color}" stroke-width="${width}" stroke-linecap="round"/>`;
const text=(v,x,y,size,color=ink)=>
  `<text x="${x}" y="${y}" dominant-baseline="central" text-anchor="middle" font-family="Hiragino Sans GB, sans-serif" font-size="${size}" font-weight="700" fill="${color}">${v}</text>`;
const disc=(x,y,r,highlight=false)=>
  `<circle cx="${x}" cy="${y}" r="${r}" fill="${highlight?gold:teal}" stroke="${highlight?coral:ink}" stroke-width="${highlight?3:1.5}"/>`;
const inset=(shape,x,y,w,h,vw,vh)=>
  `<svg x="${x}" y="${y}" width="${w}" height="${h}" viewBox="0 0 ${vw} ${vh}" preserveAspectRatio="none">${shape}</svg>`;
const panel=(w,h)=>box(2,2,w-4,h-4,mint,ink,4,21);
function register(key,w,h,svg,proof=null){art.set(key,{w,h,svg,proof});}
function arrow(x,y,xx,yy,color=coral,width=6){
  const angle=Math.atan2(yy-y,xx-x),tip=3*width;
  return line(x,y,xx,yy,color,width)+[-.5,.5].map(delta=>
    line(xx,yy,xx-tip*Math.cos(angle+delta),yy-tip*Math.sin(angle+delta),color,width)).join('');
}
function dotGrid(count,x,y,{radius=13,pitch=35,columns=3,last=false}={}){
  return Array.from({length:count},(_,i)=>disc(x+i%columns*pitch,y+Math.floor(i/columns)*pitch,radius,last&&i===count-1)).join('');
}
function mat(tens,ones,{value=true,labels=true,moved='none',illegal=false}={}){
  const model=illegal?{tens,ones,discs:tens+ones,value:null}:arrangement(tens,ones);
  const slots=[[tens,13,gold,'十位','tens'],[ones,203,mint,'个位','ones']];
  const columns=illegal?4:3;
  const rowStart=illegal?32:51;
  const places=slots.map(([n,x,tint,name,side])=>box(x,14,180,227,warm,ink,4,13)+
    box(x+6,22,168,41,tint,'none',0,8)+(labels?text(name,x+90,43,28):'')+
    dotGrid(n,x+rowStart,102,{radius:14,pitch:39,columns,last:side===moved})).join('');
  return {svg:panel(396,317)+places+(value&&model.value!==null?box(99,255,198,48,warm,ink,3,9)+text(model.value,198,279,41):''),
    model};
}
function matArt(key,tens,ones,options={}){
  const {svg,model}=mat(tens,ones,options);
  register(key,396,317,svg,{...model,moved:options.moved??'none',legal:!options.illegal});
}
function record(key,discs,{reverse=false,hidden=[],spoiled=[]}={}){
  const rows=arrangements(discs);
  if(reverse)rows.reverse();
  const w=690,h=478,y0=55,gap=Math.min(79,(h-y0-20)/rows.length);
  const svg=panel(w,h)+text('十位',180,28,29)+text('个位',382,28,29)+text('组成的数',574,28,29)+
    rows.map(({tens,ones,value},i)=>{
      const y=y0+i*gap;
      const visible=hidden.includes(value)?null:spoiled.find(([n])=>n===value)?.[1]??value;
      const r=Math.min(8.5,gap*.23),color=visible===null?'#fff9ea':warm;
      return box(16,y,655,gap-3,color,ink,2,7)+line(279,y+3,279,y+gap-6,ink,2)+line(490,y+3,490,y+gap-6,ink,2)+
        dotGrid(tens,55,y+gap*.48,{radius:r,pitch:22,columns:9})+
        dotGrid(ones,305,y+gap*.48,{radius:r,pitch:20,columns:9})+
        (visible===null?'':text(visible,581,y+gap*.48,Math.min(39,gap*.76)));
    }).join('');
  register(key,w,h,svg,{discs,rows,reverse,hidden,spoiled});
}
function number(key,value){
  register(key,176,104,box(3,3,170,98,warm,ink,4,14)+text(value,88,52,68),{value});
}
function tray(key,n,marked=false){
  register(key,265,188,panel(265,188)+box(22,20,221,147,warm,ink,3,18)+
    dotGrid(n,65,55,{radius:15,pitch:45,columns:4,last:marked}),{discs:n});
}
function compareSlots(key,from,to,side){
  const a=mat(...from),b=mat(...to,{moved:side});
  register(key,720,345,panel(720,345)+inset(a.svg,12,52,316,253,396,317)+
    inset(b.svg,392,52,316,253,396,317)+arrow(335,170,384,170),
    {from:a.model,to:b.model,moved:side});
}
function countRibbon(key,values){
  const w=710,h=170,gap=620/values.length;
  const cells=values.map((n,i)=>{
    const x=45+i*gap;
    return box(x,53,gap-7,62,warm,ink,3,8)+text(n,x+(gap-7)/2,84,Math.min(46,gap*.51));
  }).join('');
  register(key,w,h,panel(w,h)+cells,{values});
}
function coordinates(key,selected){
  const w=610,h=462,left=62,top=36,dx=51,dy=39;
  const result=Array.from({length:10},(_,t)=>Array.from({length:10},(_,o)=>{
    const cell=arrangement(t,o),x=left+o*dx,y=top+t*dy,mark=cell.discs===selected;
    return box(x,y,dx-3,dy-3,mark?gold:warm,mark?coral:ink,mark?4:1,5)+text(cell.value,x+24,y+18,23);
  }).join('')).join('');
  register(key,w,h,panel(w,h)+result,{selected,selectedValues:arrangements(selected).map(p=>p.value),origin:0});
}
function capacityLimits(key){
  const left=mat(0,10,{illegal:true,value:false}),right=mat(10,0,{illegal:true,value:false});
  const cross=x=>line(x-34,287,x+34,337)+line(x+34,287,x-34,337);
  register(key,710,352,panel(710,352)+inset(left.svg,20,34,311,249,396,317)+
    inset(right.svg,379,34,311,249,396,317)+cross(176)+cross(535),{discs:10,invalid:[[0,10],[10,0]]});
}
matArt('one-in-ones',0,1);
matArt('one-in-tens',1,0);
compareSlots('two-discs-move', [0,2],[1,1],'tens');
record('two-disc-record',2);
record('three-missing-21',3,{hidden:[21]});
record('three-complete',3);
record('four-up',4);
record('four-down',4,{reverse:true});
record('five-complete',5);
coordinates('same-six-diagonal',6);
countRibbon('nine-prediction',[0,1,2,3,4,5,6,7,8,9]);
record('six-record-error',6,{hidden:[51],spoiled:[[33,34]]});
record('six-record-fixed',6);
capacityLimits('ten-cannot-fit-one-side');
record('ten-legal-record',10);
tray('family-paper-discs',8);
matArt('family-blank-mat',0,0,{value:false});
tray('maze-ready',2);
matArt('depot-ready',1,2,{value:false});
register('maze-exit',114,115,box(5,8,104,99,gold,ink,4,16)+box(19,21,75,74,mint,ink,3,14)+
  arrow(35,58,82,58),{type:'exit'});
for(const direction of ['left','right']){
  const [x,xx]=direction==='left'?[126,28]:[28,126];
  register('move-'+direction,155,91,panel(155,91)+arrow(x,45,xx,45,coral,9),{direction});
}
export const mazePlans=[{discs:2,step:1},{discs:4,step:1},{discs:5,step:-1}];
export const depotPlans=[[[1,2],[2,2]],[[3,1],[3,2],[3,3]],[[2,1],[4,1],[4,2],[5,1]]];
const compactMats=new Map();
const firstMats=new Set();
for(const {discs,step} of mazePlans){
  const sequence=arrangements(discs);
  firstMats.add((step>0?sequence[0]:sequence.at(-1)).value);
  for(const model of sequence)compactMats.set(model.value,model);
}
for(const [tens,ones] of depotPlans.flat()){
  const model=arrangement(tens,ones);
  compactMats.set(model.value,model);
}
for(const {tens,ones,value} of compactMats.values()){
  if(!firstMats.has(value))matArt('game-mat-'+value,tens,ones,{value:false,labels:false});
  matArt('large-mat-'+value,tens,ones,{value:true,labels:true});
}
for(const n of [3,4,5,6])tray('budget-'+n,n);

matArt('q-new-board-43',4,3,{value:false});
for(const n of [34,43,7,8,9,17,36,62,6,10])number('q-number-'+n,n);
matArt('q-move-start-35',3,5,{value:false});
matArt('q-move-a-44',4,4,{value:false});
matArt('q-move-b-26',2,6,{value:false});
matArt('q-move-c-45',4,5,{value:false});
tray('q-seven-budget',7);
tray('q-eight-budget',8);
tray('q-eleven-budget',11);
matArt('q-eleven-a',9,2,{value:false});
matArt('q-eleven-b',10,1,{value:false,illegal:true});
matArt('q-eleven-c',1,10,{value:false,illegal:true});
countRibbon('q-reverse-54-72',[54,72]);

export const definitions=Object.fromEntries([...art].map(([key,{proof}])=>[key,proof]));
if(process.argv.includes('--describe'))console.log(JSON.stringify(definitions));
else if(process.argv[1]===fileURLToPath(import.meta.url)){
  await mkdir(fileURLToPath(new URL('../assets/',import.meta.url)),{recursive:true});
  for(const [key,{w,h,svg}] of art){
    const source=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${svg}</svg>`;
    await sharp(Buffer.from(source)).png({compressionLevel:9}).toFile(target(key));
  }
}

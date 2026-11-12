import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const path=key=>fileURLToPath(new URL('../assets/'+key+'.png',import.meta.url));
const gold='#f3c674',pine='#234c40',mint='#d7ede1',paper='#fff1d1',red='#a64329',blue='#17657b';
const art=new Map();
export const chart=Array.from({length:10},(_,row)=>Array.from({length:10},(_,col)=>10*row+col+1));
export function location(value){
  if(!Number.isInteger(value)||value<1||value>100)throw new RangeError('expected a ticket from 1 to 100');
  return [Math.floor((value-1)/10),(value-1)%10];
}
export function neighbor(value,down,right){
  const [row,col]=location(value);
  return chart[row+down]?.[col+right]??null;
}
const rect=(x,y,w,h,fill,stroke=pine,sw=3,r=10)=>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
const text=(v,x,y,size,color=pine)=>
  `<text x="${x}" y="${y}" dominant-baseline="central" text-anchor="middle" font-family="sans-serif" font-size="${size}" font-weight="700" fill="${color}">${v}</text>`;
const line=(x,y,xx,yy,color=red,width=7)=>
  `<path d="M${x} ${y}L${xx} ${yy}" stroke="${color}" stroke-width="${width}" stroke-linecap="round"/>`;
const circle=(x,y,r,color)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="${color}"/>`;
function arrow(x,y,xx,yy,color=red,width=7){
  const angle=Math.atan2(yy-y,xx-x),point=3.2*width;
  return line(x,y,xx,yy,color,width)+[-.54,.54].map(d=>
    line(xx,yy,xx-point*Math.cos(angle+d),yy-point*Math.sin(angle+d),color,width)).join('');
}
function register(key,w,h,svg,proof=null){art.set(key,{w,h,svg,proof});}
function seat(value,x,y,w,h,{active=false,mark=[],ticket=true}={}){
  const marks=mark.map(kind=>{
    if(kind==='tens')return line(x+w*.21,y+h*.82,x+w*.78,y+h*.82,red,Math.max(2,w*.042));
    if(kind==='ones')return circle(x+w*.82,y+h*.23,Math.max(2,w*.066),blue);
    return `<path d="M${x+w*.13} ${y+h*.13}h${w*.21}l${-w*.21} ${h*.25}Z" fill="#446e44"/>`;
  }).join('');
  return rect(x,y,w,h,active?gold:value==null?'#fbf8e9':ticket?paper:mint,active?red:pine,active?5:2,Math.min(w,h)*.14)+
    (value==null?'':text(value,x+w*.5,y+h*.49,Math.min(w*.43,h*.58)))+marks;
}
function windowArt(key,rows,{marked=()=>[],active=[],hidden=[],route=[]}={}){
  const w=700,h=395;
  const bounds={left:25,top:21,right:675,bottom:374};
  const positions={};
  const matrix=rows.map(row=>row.map(n=>n===null?null:location(n)));
  const columns=Math.max(...rows.map(row=>row.length));
  const dx=Math.min(130,(bounds.right-bounds.left)/columns);
  const dy=Math.min(106,(bounds.bottom-bounds.top)/rows.length);
  const x0=(w-columns*dx)/2,y0=(h-rows.length*dy)/2;
  const cells=rows.map((row,r)=>row.map((n,c)=>{
    const x=x0+c*dx,y=y0+r*dy;
    positions[r+','+c]=[x+dx/2,y+dy/2];
    if(n!==null)positions[n]=[x+dx/2,y+dy/2];
    return seat(hidden.includes(n)?null:n,x+2,y+2,dx-4,dy-4,{active:active.includes(n)&&n!==null,mark:marked(n),ticket:r%2===0});
  }).join('')).join('');
  const arrows=route.map(([from,to,direction])=>{
    const [x,y]=positions[from],[xx,yy]=positions[to];
    if(direction==='wrap'){
      const edge=y0-27,turn=x0-12;
      return line(x,y-dy*.44,x,edge,red,5)+line(x,edge,turn,edge,red,5)+line(turn,edge,turn,yy,red,5)+
        arrow(turn,yy,xx-dx*.32,yy,red,5);
    }
    const ratio=.27;
    return arrow(x+(xx-x)*ratio,y+(yy-y)*ratio,xx-(xx-x)*ratio,yy-(yy-y)*ratio,red,5);
  }).join('');
  register(key,w,h,rect(2,2,w-4,h-4,'#e1eddb',pine,4,21)+cells+arrows,{rows,matrix,active,hidden,route});
}
function largeChart(key,mark=()=>[],active=[],hidden=[]){
  const w=660,h=497,x0=30,y0=17,dx=60,dy=46;
  const cells=chart.map((row,r)=>row.map((n,c)=>seat(hidden.includes(n)?null:n,x0+c*dx,y0+r*dy,dx-3,dy-3,
    {active:active.includes(n),mark:mark(n),ticket:r%2===0})).join('')).join('');
  register(key,w,h,rect(2,2,w-4,h-4,'#e4edda',pine,4,23)+cells,
    {rows:chart,active,hidden,marks:Object.fromEntries(chart.flat().map(n=>[n,mark(n)]).filter(([,marks])=>marks.length))});
}
function badge(key,n){
  register(key,142,98,seat(n,4,4,134,90),{number:n,location:location(n)});
}
function direction(key,mode){
  const color=mode==='left'?blue:red;
  const from={right:[28,70,167,70],left:[167,70,28,70],down:[97,24,97,120],up:[97,120,97,24]}[mode];
  register(key,194,140,rect(4,4,186,132,paper,pine,4,15)+arrow(...from,color,13),{mode});
}

const pattern=n=>{
  if(n==null)return [];
  const tens=Math.floor(n/10)%10,ones=n%10;
  return [...(tens===4?['tens']:[]),...(ones===4?['ones']:[]),...(n>=10&&n<100&&tens===ones?['same']:[])];
};
windowArt('first-ticket-row',[chart[0],chart[1]],{active:[1,10,11],hidden:[2,5,12,13,14,15,16,17,18,19,20]});
windowArt('build-first-two-rows',[chart[0],chart[1]],{active:[1,10,11]});
windowArt('row-62-to-64',[[61,62,63,64,65]],{active:[62,63],route:[[62,63]]});
windowArt('row-middle-gap',[[62,63,64]],{active:[63],hidden:[63]});
largeChart('full-hundred-chart',()=>[],[49,50,51,100]);
// A true wrap uses the last cells and first cells of separate, complete rows.
windowArt('wrap-whole-rows',[chart[4],chart[5]],{active:[49,50,51],route:[[50,51,'wrap']]});
windowArt('same-column-27',[[27],[37],[47]],{active:[27,37,47],route:[[27,37],[37,47]]});
windowArt('same-column-zero',[[70],[80],[90],[100]],{active:[70,80,90,100]});
largeChart('three-digit-marks',pattern,[40,44,100]);
windowArt('zoom-four-pattern',[chart[3],chart[4]],{marked:pattern,active:[40,44]});
windowArt('left-diagonal-65',[[64,65,66],[74,75,76]],{active:[65,75,74],route:[[65,75],[75,74]]});
windowArt('right-diagonal-65',[[64,65,66],[74,75,76]],{active:[65,75,76],route:[[65,75],[75,76]]});
windowArt('cross-two-checks',[[55,56],[65,66]],{active:[55,66],hidden:[66]});
windowArt('cross-proven-66',[[55,56],[65,66]],{active:[55,56,65,66],route:[[55,56],[56,66],[55,65],[65,66]]});
windowArt('partner-new-fragment',[[76,77],[86,87],[96,97]],{active:[77,87,96],hidden:[76,86,97]});
windowArt('skip-a-ticket',[[21,22,23,24,25,26,27]],{active:[21,23,25,27]});
windowArt('home-draw-your-own',[[4,5],[14,15]],{active:[5,14],hidden:[4,15]});
for(const mode of ['right','left','up','down'])direction('rule-'+mode,mode);

export const hops=[
  {start:16,route:[17,18,19],distractors:[20,15],sign:1},
  {start:58,route:[59,60,61],distractors:[57,62],sign:1},
  {start:88,route:[87,86,85,84],distractors:[89,83],sign:-1},
];
export const matches=[
  {down:1,bottom:[24,26],pieces:[34]},
  {down:-1,bottom:[63,78],pieces:[53,68]},
  {down:1,bottom:[32,46,57],pieces:[42,56,67]},
];
for(const n of new Set([...hops.flatMap(h=>[h.start,...h.route,...h.distractors]),
  ...matches.flatMap(l=>[...l.bottom,...l.pieces])]))badge('ticket-'+n,n);
for(const h of hops){
  for(let i=0;i<h.route.length;i++){
    const n=h.route[i],before=i?h.route[i-1]:h.start;
    if(before%10===0&&n===before+1){
      windowArt('hop-proof-'+n,[chart[location(before)[0]],chart[location(n)[0]]],{active:[before,n],route:[[before,n,'wrap']]});
    }else{
      windowArt('hop-proof-'+n,[h.sign>0?[before,n]:[n,before]],{active:[before,n],route:[[before,n]]});
    }
  }
}
for(const {down,pieces} of matches){
  for(const n of pieces){
    const prev=neighbor(n,-down,0);
    windowArt('tile-proof-'+n,down>0?[[prev],[n]]:[[n],[prev]],{active:[n,prev],route:[[prev,n]]});
  }
}
windowArt('hop-ready',[[15,16,17,18,19]],{active:[16],hidden:[17,18,19]});
windowArt('tiles-ready',[[24],[34]],{active:[24],hidden:[34]});

windowArt('q-horizontal-gap',[[12,13,14]],{active:[13],hidden:[13]});
windowArt('q-vertical-gap',[[28],[38],[48]],{active:[48],hidden:[48]});
for(const n of [15,11,13,48,39,47,81,92,82,25,35,27])badge('q-ticket-'+n,n);
windowArt('q-wrap-stem',[chart[2],chart[3]],{active:[30],hidden:chart[3]});
windowArt('q-wrap-a',[chart[2],chart[3]],{active:[30,32],hidden:chart[3].filter(n=>n!==32)});
windowArt('q-wrap-b',[chart[2],chart[3]],{active:[30,31],hidden:chart[3].slice(1)});
windowArt('q-wrap-c',[chart[2],chart[3]],{active:[30,40],hidden:chart[3].slice(0,-1)});
windowArt('q-tens-stem',[chart[8],chart[9]]);
windowArt('q-tens-a',[chart[8],chart[9]],{marked:n=>n>=91?['tens']:[]});
windowArt('q-tens-b',[chart[8],chart[9]],{marked:n=>n>=81&&n<=90?['tens']:[]});
windowArt('q-tens-c',[chart[8],chart[9]],{marked:n=>n>=90&&n<=99?['tens']:[]});
windowArt('q-diagonal-stem',[[72,73,74],[82,83,84]],{active:[73],hidden:[72,74,82,83,84],route:[[73,83],[83,82]]});
windowArt('q-fragment-stem',[[15,16],[25,26]],{active:[25],hidden:[16,25]});

export const definitions=Object.fromEntries([...art].map(([key,{proof}])=>[key,proof]));
if(process.argv.includes('--describe'))console.log(JSON.stringify(definitions));
else if(process.argv[1]===fileURLToPath(import.meta.url)){
  await mkdir(fileURLToPath(new URL('../assets/',import.meta.url)),{recursive:true});
  for(const [key,{w,h,svg}] of art){
    const source=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${svg}</svg>`;
    await sharp(Buffer.from(source)).png({compressionLevel:9}).toFile(path(key));
  }
}

import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const output=name=>fileURLToPath(new URL('../assets/'+name+'.png',import.meta.url));
const ink='#193f40', paper='#fbf2dd', blue='#427c8a', blueLight='#d7e7e8';
const orange='#c97532', orangeLight='#f7e0b3', line='#8b9b81';
const art=new Map();

export function regroup(a,b){
  const whole=a>=10?a:b, added=a>=10?b:a;
  if(!Number.isInteger(whole)||whole<10||whole>99||
     !Number.isInteger(added)||added<1||added>9||whole+added>100){
    throw new RangeError('Expected a two-digit number and a positive one-digit addend within 100');
  }
  const tens=Math.floor(whole/10), old=whole%10;
  const loose=old+added, carry=Math.floor(loose/10), left=loose%10;
  return {a,b,whole,tens,old,added,loose,carry,left,total:tens*10+loose};
}
function remember(id,w,h,body,proof,fact){
  if(art.has(id))throw new Error('Duplicate diagram '+id);
  art.set(id,{w,h,body,proof,fact});
}
const rect=(x,y,w,h,r,fill,stroke='none',sw=0)=>
  '<rect x="'+x+'" y="'+y+'" width="'+w+'" height="'+h+'" rx="'+r+'" fill="'+fill+'" stroke="'+stroke+'" stroke-width="'+sw+'"/>';
const label=(s,x,y,size,color=ink)=>'<text x="'+x+'" y="'+y+'" text-anchor="middle" dominant-baseline="central" font-family="sans-serif" font-weight="700" font-size="'+size+'" fill="'+color+'">'+s+'</text>';
const at=(x,y,s,content)=>'<g transform="translate('+x+' '+y+') scale('+s+')">'+content+'</g>';
function bookmark(x,y,size,color){
  const path='M '+(-.30*size)+' '+(-.43*size)+' H '+(.30*size)+' V '+(.44*size)+
    ' L 0 '+(.27*size)+' L '+(-.30*size)+' '+(.44*size)+' Z';
  return '<g transform="translate('+x+' '+y+')"><path d="'+path+'" fill="'+color+
    '" stroke="'+ink+'" stroke-width="'+Math.max(1,size*.045)+'"/>'+
    '<circle cy="'+(-size*.20)+'" r="'+size*.055+'" fill="'+paper+'"/></g>';
}
const series=(n,draw)=>Array.from({length:n},(_,i)=>draw(i)).join('');
const loose=(n,x,y,step,columns,color)=>series(n,i=>
  bookmark(x+i%columns*step,y+Math.floor(i/columns)*step,step*.86,color));
function tenPack(x,y,size,color){
  const a=color===orange?orangeLight:blueLight;
  return at(x,y,size/66,rect(0,0,65,47,7,a,color,3)+
    series(10,i=>rect(7+i*5.25,8,3.6,27,1.5,color))+
    rect(0,17,65,14,5,a,ink,1.2)+label(10,32.5,24.5,12));
}
function packs(n,x,y,size,cols,color=blue){
  return series(n,i=>tenPack(x+(size+7)*(i%cols),y+(size*.75+8)*Math.floor(i/cols),size,color));
}
function frame(n,x,y,step,old=n){
  return rect(x-step*.55,y-step*.55,step*5.1,step*2.1,step*.16,blueLight,blue,3)+series(10,i=>{
    const cx=x+i%5*step,cy=y+Math.floor(i/5)*step;
    return rect(cx-step*.44,cy-step*.44,step*.88,step*.88,step*.10,paper,line,1.7)+
      (i<n?bookmark(cx,cy,step*.78,i<old?blue:orange):'');
  });
}
function composeBefore(m,{split=false}={}){
  const left=m.a<m.b&&m.a<10;
  const main=rect(12,16,656,209,21,paper,line,3)+
    rect(22,36,left?161:469,145,14,left?orangeLight:blueLight)+
    rect(left?197:507,36,left?461:151,145,14,left?blueLight:orangeLight);
  const storedX=left?215:36, oldX=left?477:303,newX=left?44:532;
  return main+packs(m.tens,storedX,65,44,5)+loose(m.old,oldX,74,34,5,blue)+
    loose(m.added,newX,70,29,4,orange)+label('+',left?190:499,109,36)+
    (split?label(m.tens*10+'  +  '+m.old+'    +    '+m.added,340,204,35):
      label(m.a+' + '+m.b,340,204,37));
}
function composePacked(tens,left,{number=true,newTen=false,old=tens-(newTen?1:0)}={}){
  const digits=10*tens+left;
  const storage=rect(20,33,406,128,13,blueLight,blue,2.5);
  const looseArea=rect(440,33,218,128,13,orangeLight,orange,2.5);
  const holders=packs(old,41,49,52,6);
  const x=41+(52+7)*(old%6),y=49+(52*.75+8)*Math.floor(old/6);
  return storage+looseArea+holders+(newTen?tenPack(x,y,52,orange):'')+
    loose(left,471,65,35,5,orange)+
    (number?label(digits,340,207,53):'');
}
function looseResult(m,showOriginal=false){
  const inFrame=Math.min(10,m.loose);
  return rect(14,22,652,200,19,paper,line,3)+frame(inFrame,60,68,45,m.old)+
    (m.carry?rect(287,42,173,116,13,orangeLight,orange,2.5)+loose(m.left,315,72,34,4,orange):'')+
    (showOriginal?packs(m.tens,481,47,42,3):'')+
    label(m.old+' + '+m.added+' = '+m.loose,340,192,43);
}
function exchanged(looseCount,oldCount){
  const m={loose:looseCount,old:oldCount,carry:Math.floor(looseCount/10),left:looseCount%10};
  return rect(14,18,652,210,20,paper,line,3)+frame(10,48,67,30,oldCount)+
    label('→',232,89,53,orange)+tenPack(283,57,96,orange)+
    label('+',427,90,43)+loose(m.left,480,69,39,5,orange)+
    label(m.loose+' = 10 + '+m.left,340,180,45);
}
function before(id,a,b,{w=680,h=238,fact=0,split=false}={}){
  const model=regroup(a,b);
  remember(id,w,h,at(0,(h-238*w/680)/2,w/680,composeBefore(model,{split})),{layout:'before',model},fact);
}
function finish(id,tens,left,{w=680,h=238,fact=1,newTen=false,number=true,model}={}){
  remember(id,w,h,at(0,(h-238*w/680)/2,w/680,composePacked(tens,left,{number,newTen})),
    {layout:'packed',tens,left,quantity:10*tens+left,newTen,...(model?{model}:{})},fact);
}
function ready(id,body,proof,fact){
  remember(id,680,238,body,proof,fact);
}

const main=regroup(27,6);
before('lesson-27-plus-6',27,6);
before('lesson-27-split',27,6,{split:true});
ready('lesson-13-loose',looseResult(main),{layout:'fill',model:main,frameCount:10,outside:3},1);
ready('lesson-13-exchange',exchanged(13,7),{layout:'exchange',model:main,removedLoose:10,newTens:1,left:3},2);
finish('lesson-33-finished',3,3,{newTen:true,model:main});
ready('lesson-33-equations',
  label('27 = 20 + 7',340,39,47)+rect(108,76,464,61,13,orangeLight,orange,2)+
  label('7 + 6 = 13',340,107,47)+rect(108,150,464,61,13,blueLight,blue,2)+
  label('20 + 13 = 33',340,181,47),{layout:'two-equations',model:main},1);
for(const added of [4,9]){
  const m=regroup(52,added);
  ready('lesson-52-plus-'+added,looseResult(m,true),{layout:'fill',model:m,frameCount:Math.min(10,m.loose),outside:m.carry?m.left:0,originalPacksShown:m.tens},2);
}
const exact=regroup(72,8);
ready('lesson-72-plus-8',looseResult(exact,true),{layout:'fill',model:exact,frameCount:10,outside:0,originalPacksShown:exact.tens},2);
finish('lesson-80-finished',8,0,{newTen:true,model:exact,fact:2});
before('lesson-8-plus-56',8,56,{fact:3});
finish('lesson-64-finished',6,4,{newTen:true,model:regroup(8,56),fact:3});
before('lesson-48-plus-9',48,9,{fact:3});
finish('lesson-57-audit',5,7,{newTen:true,model:regroup(48,9),fact:3});
before('family-69-plus-6',69,6,{fact:1});
ready('family-verify-75',at(110,9,.67,composePacked(7,5,{newTen:true,number:false}))+
  rect(37,168,606,51,12,blueLight,blue,2)+label('69 → 70 → 71 → 72 → 73 → 74 → 75',340,194,32),
  {layout:'count-on',model:regroup(69,6),steps:[69,70,71,72,73,74,75]},1);

ready('tiles-ready',
  rect(26,18,628,205,22,blueLight,blue,3)+loose(5,117,82,43,5,blue)+
  label('+',338,93,44)+loose(6,406,78,43,4,orange)+label('5 + 6 → 11',340,184,40),
  {layout:'loose-pair',old:5,added:6,quantity:11},1);
for(const [kind,counts] of [['old',[5,7,8,9]],['new',[3,4,5,6,7,8,9]]]){
  for(const count of counts){
    remember('tile-'+kind+'-'+count,182,176,
      rect(4,4,174,168,18,kind==='old'?blueLight:orangeLight,kind==='old'?blue:orange,3)+
      loose(count,32,32,39,4,kind==='old'?blue:orange)+label(count,91,149,41),
      {layout:'single-loose-pile',count,kind},1);
  }
}
for(const [old,added] of [[5,6],[8,3],[7,6],[9,4],[8,5],[9,7],[8,8],[7,9]]){
  const total=old+added;
  remember('tile-proof-'+old+'-'+added,470,216,
    rect(0,0,470,216,21,paper,blue,4)+at(6,3,.69,exchanged(total,old)),
    {layout:'exchange',old,added,total,newTens:1,left:total-10},2);
}
before('depot-ready',38,5);
for(const [a,b] of [[38,5],[47,6],[63,7],[35,8],[9,45],[7,58],[76,6],[84,7],[26,9]]){
  const m=regroup(a,b),key=a+'-'+b;
  remember('crate-'+key,220,220,
    rect(0,0,220,220,20,paper,blue,4)+label(a+'+'+b,110,36,61)+
    packs(m.tens,26,74,27,5)+loose(m.old,31,171,15,5,blue)+loose(m.added,122,171,15,5,orange),
    {layout:'cargo-summary',model:m},0);
  before('order-'+key,a,b,{w:452,h:260,fact:0});
  finish('packed-'+key,m.tens+m.carry,m.left,{w:452,h:260,fact:3,newTen:true,model:m});
}
for(const total of [35,43,53,54,65,70,82,91]){
  remember('dock-'+total,182,182,rect(6,6,170,170,27,blueLight,ink,5)+
    label(total,91,89,97),{layout:'number-target',total},3);
}

ready('q-fill-empty-frame',frame(0,200,75,66),{layout:'empty-frame',capacity:10},2);
for(const [suffix,a,b] of [['a',34,5],['b',58,4],['c',62,3]]){
  before('q-fill-'+suffix,a,b,{w:432,h:182,fact:2});
}
before('q-first-49-6',49,6,{fact:1});
before('q-final-67-5',67,5,{fact:1});
before('q-exact-54-6',54,6,{fact:2});
before('q-left-7-76',7,76,{fact:3});
const audit=regroup(65,8);
ready('q-audit-65-8',at(0,5,.75,composeBefore(audit))+
  rect(520,30,141,160,17,orangeLight,orange,3)+label('63 ?',590,106,44),
  {layout:'undercount',model:audit,statedTotal:63},3);
for(const [section,counts,fact] of [
  ['first',[[1,5],[5,5],[1,4]],1],
  ['final',[[6,2],[8,2],[7,2]],1],
  ['exact',[[5,0],[6,0],[6,1]],2],
  ['left',[[8,3],[7,3],[8,2]],3],
  ['audit',[[6,3],[8,3],[7,3]],3],
]){
  for(const [i,[tens,left]] of counts.entries()){
    finish('q-'+section+'-'+'abc'[i],tens,left,{w:432,h:170,fact});
  }
}

export const diagramProof=()=>Object.fromEntries([...art].map(([key,d])=>[key,{...d.proof,fact:d.fact}]));

async function render(id,d){
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+d.w+'" height="'+d.h+'">'+
    rect(0,0,d.w,d.h,12,paper)+d.body+'</svg>';
  await sharp(Buffer.from(svg)).png().toFile(output(id));
}
if(process.argv.includes('--describe'))console.log(JSON.stringify(diagramProof()));
else if(process.argv[1]===fileURLToPath(import.meta.url))for(const [id,d] of art)await render(id,d);


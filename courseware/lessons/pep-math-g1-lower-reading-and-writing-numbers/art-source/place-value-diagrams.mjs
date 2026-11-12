import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const asset=key=>fileURLToPath(new URL('../assets/'+key+'.png',import.meta.url));
const art=new Map();
const warm='#fff1d3',pine='#214a40',mint='#cce7da',coral='#aa412b',gold='#f1c875';
const dependencies=['single-envelope','post-desk','chart-counter','maze-garden','delivery-street',
  'maze-car','postal-arch','maze-plant','carrier-stand','postbox'];
const input=Object.fromEntries(await Promise.all(dependencies.map(async key=>[key,
  'data:image/png;base64,'+(await sharp(asset(key)).resize(700,400,{fit:'inside',withoutEnlargement:true}).png().toBuffer()).toString('base64'),
])));
const box=(x,y,w,h,fill,stroke='none',width=0,r=12)=>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${width}"/>`;
const oval=(x,y,rx,ry,fill,stroke=pine,width=2)=>
  `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="${fill}" stroke="${stroke}" stroke-width="${width}"/>`;
const line=(x,y,xx,yy,color=pine,width=6)=>
  `<path d="M${x} ${y}L${xx} ${yy}" stroke="${color}" stroke-width="${width}" stroke-linecap="round"/>`;
const text=(value,x,y,size,color=pine)=>
  `<text x="${x}" y="${y}" text-anchor="middle" dominant-baseline="central" font-family="Hiragino Sans GB, sans-serif" font-weight="700" font-size="${size}" fill="${color}">${value}</text>`;
const picture=(key,x,y,w,h)=>
  `<image x="${x}" y="${y}" width="${w}" height="${h}" href="${input[key]}" preserveAspectRatio="xMidYMid meet"/>`;
const inset=(shape,x,y,w,h,vw,vh)=>
  `<svg x="${x}" y="${y}" width="${w}" height="${h}" viewBox="0 0 ${vw} ${vh}" preserveAspectRatio="none">${shape}</svg>`;

export function placeValue(n){
  if(!Number.isInteger(n)||n<0||n>99)throw new RangeError('expected 0–99');
  const tens=Math.floor(n/10),ones=n%10;
  return {n,tens,ones,groupSize:10};
}
function register(key,w,h,svg,inputs=[],quantity=null){
  art.set(key,{w,h,svg,inputs,quantity});
}
function envelope(x,y,w,h){
  return picture('single-envelope',x,y,w,h);
}
function tray(x,y,w,h){
  return box(x,y,w,h,mint,pine,Math.max(2,w*.025),w*.085)+
    Array.from({length:10},(_,i)=>envelope(x+w*(.08+(i%5)*.17),y+h*(.13+Math.floor(i/5)*.39),
      w*.155,h*.30)).join('');
}
function groups(model){
  const count=model.tens;
  const rack=box(14,43,445,307,'#fff5dce8',pine,3,17)+
    box(479,43,225,307,'#eef5e9ed',pine,3,17);
  const trays=Array.from({length:count},(_,i)=>tray(33+(i%3)*141,70+Math.floor(i/3)*86,126,75));
  const singles=Array.from({length:model.ones},(_,i)=>envelope(497+(i%3)*62,89+Math.floor(i/3)*75,55,44));
  return rack+trays.join('')+singles.join('');
}
function abacus(model,{slots=false,select='none',compact=false,onlyOnes=false}={}){
  const cut=slots?238:288;
  const pitch=compact?27:24;
  const centers=[104,256],beadColors=['#d17a39','#1b8b7b'];
  const slotsArt=slots?centers.map((x,i)=>{
    if(i===0&&onlyOnes)return '';
    const selected=select==='both'||select===(i?'ones':'tens');
    return box(x-67,299,134,70,selected?gold:'#fffdf2',selected?coral:pine,4,10)+
      text(i?model.ones:model.tens,x,334,55);
  }).join(''):'';
  return box(6,6,348,slots?370:362,warm,pine,5,23)+
    centers.map((x,i)=>{
      const units=i?model.ones:model.tens;
      if(i===0&&onlyOnes)return '';
      return line(x,29,x,cut,pine,9)+
        Array.from({length:units},(_,k)=>oval(x,cut-14-k*pitch,compact?49:40,compact?11:10,
          beadColors[i],pine,2)).join('')+
        box(x-67,cut+6,134,50,i?mint:'#f8d396',pine,3,8)+
        text(i?'个位':'十位',x,cut+30,36);
    }).join('')+slotsArt;
}
function slotOnly(digits=[],selection='none'){
  return box(3,3,354,204,'#e4eee4',pine,5,17)+
    [93,267].map((x,i)=>{
      const lit=selection==='both'||selection===(i?'ones':'tens');
      return box(x-72,18,144,49,i?mint:'#f8d396',pine,3,8)+
        text(i?'个位':'十位',x,43,35)+
        box(x-72,79,144,109,lit?gold:'#fffaf0',lit?coral:pine,lit?7:3,9)+
        (digits[i]===undefined?'':text(digits[i],x,133,76));
    }).join('');
}
function labelCard(n,w=360,h=205){
  return box(8,8,w-16,h-16,warm,pine,6,19)+
    box(22,27,w-44,18,mint,'none',0,7)+
    text(n,w/2,h*.60,h*.49);
}
function ear(){
  return box(5,5,350,277,'#f5e4bc',pine,6,29)+
    '<path d="M164 219c-23 0-45-14-45-42 0-18 9-26 19-39 13-16 15-26 15-40 0-31 24-51 53-51 34 0 60 22 60 56 0 22-10 35-28 51-16 14-16 34-25 46-9 12-24 19-49 19Z" fill="#edaa78" stroke="#854935" stroke-width="8"/>'+
    '<path d="M180 128c-8-28 4-48 29-48 19 0 27 11 27 23 0 14-16 21-24 31-7 10-6 25-18 30" fill="none" stroke="#854935" stroke-width="8" stroke-linecap="round"/>'+
    '<path d="M80 88q-44 38 0 78m-17-98q-63 60 0 120" fill="none" stroke="#247a6a" stroke-width="9" stroke-linecap="round"/>';
}
function board(key,n){
  const m=placeValue(n);
  register(key,720,400,
    picture('chart-counter',0,0,720,400)+inset(abacus(m,{slots:true}),196,12,328,376,360,382),
    ['chart-counter'],m);
}
function groupArt(key,n,backdrop){
  const m=placeValue(n);
  register(key,720,400,(backdrop?picture(backdrop,0,0,720,400):box(1,1,718,398,warm,pine,2,20))+groups(m),
    ['single-envelope',...(backdrop?[backdrop]:[])],m);
}
register('tray-of-ten',720,400,picture('post-desk',0,0,720,400)+box(29,46,664,304,'#fff2d5ed',pine,4,22)+
  tray(58,80,470,228)+envelope(553,116,110,88)+envelope(552,208,110,88),
  ['post-desk','single-envelope'],placeValue(12));
groupArt('groups-42',42,'post-desk');
groupArt('groups-66',66,'post-desk');
register('abacus-42',720,400,picture('chart-counter',0,0,720,400)+
  inset(abacus(placeValue(42)),190,13,340,375,360,376),['chart-counter'],placeValue(42));
for(const n of [42,24,50,63,17,10])board('board-'+n,n);
register('same-six',720,400,picture('chart-counter',0,0,720,400)+
  inset(abacus(placeValue(66),{slots:true,select:'both'}),181,9,358,382,360,382),
  ['chart-counter'],placeValue(66));
register('compare-50-and-5',720,400,box(3,3,714,394,'#dcebdc',pine,4,25)+
  inset(abacus(placeValue(50),{slots:true,select:'ones'}),43,14,288,366,360,382)+
  inset(abacus(placeValue(5),{slots:true,onlyOnes:true}),371,14,288,366,360,382),
  [],[placeValue(50),placeValue(5)]);
register('listen-symbol',360,287,ear());
register('speech-63',720,400,box(3,3,714,394,'#deeadc',pine,4,22)+
  inset(ear(),26,100,259,207,360,287)+
  inset(slotOnly(),333,100,361,207,360,210),[],null);
register('two-empty-places',360,210,slotOnly());

for(const n of [34,70,72,46,64]){
  const m=placeValue(n);
  register('maze-'+n,280,328,inset(abacus(m),0,0,280,328,360,376),[],m);
}
for(const digit of [0,2,3,4,6,7]){
  register('digit-'+digit,72,72,text(digit,36,37,59),[],{digit});
}
const deliveries=[31,13,80,83,8,47,74,61];
function numberedBox(n){
  return picture('postbox',22,3,136,170)+box(40,98,100,65,warm,pine,3,9)+text(n,90,130,56);
}
for(const n of deliveries){
  const m=placeValue(n);
  register('goods-'+n,180,180,inset(abacus(m,{compact:true}),0,0,180,180,360,376),[],m);
  register('box-'+n,180,180,numberedBox(n),['postbox'],m);
}
register('maze-ready',720,400,picture('maze-garden',0,0,720,400)+
  picture('maze-plant',10,221,147,170)+picture('maze-car',175,170,141,177)+
  picture('postal-arch',538,136,175,214)+inset(slotOnly(),340,164,190,110,360,210),
  ['maze-garden','maze-plant','maze-car','postal-arch']);
register('delivery-ready',720,400,picture('delivery-street',0,0,720,400)+
  inset(ear(),64,88,197,158,360,287)+picture('carrier-stand',308,166,158,182)+
  inset(numberedBox(31),531,128,144,144,180,180),
  ['delivery-street','carrier-stand','postbox'],placeValue(31));

register('q-abacus-53',490,315,box(3,3,484,309,'#dcebdd',pine,4,16)+
  inset(abacus(placeValue(53)),106,12,278,288,360,376),[],placeValue(53));
for(const n of [53,35,58,6,61,60,25,52,56,14,40,41,73]){
  register('q-number-'+n,360,205,labelCard(n),[],placeValue(n));
}
for(const [kind,selection] of [['same','none'],['ones','ones'],['tens','tens'],['both','both']]){
  register('q-'+kind+'-88',360,210,slotOnly([8,8],selection),[],{...placeValue(88),selection});
}
register('q-hear-empty',520,310,box(3,3,514,304,'#e4eddb',pine,4,18)+
  inset(ear(),17,75,174,139,360,287)+
  inset(abacus(placeValue(60),{compact:true}),220,9,277,292,360,376),
  [],placeValue(60));
groupArt('q-groups-41',41);
for(const n of [73,37,70])groupArt('q-amount-'+n,n);

export const definitions=Object.fromEntries([...art].map(([key,{inputs,quantity}])=>[key,{inputs,quantity}]));
if(process.argv.includes('--describe'))console.log(JSON.stringify(definitions));
else if(process.argv[1]===fileURLToPath(import.meta.url)){
  for(const [key,{w,h,svg}] of art){
    const doc=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${svg}</svg>`;
    await sharp(Buffer.from(doc)).png({compressionLevel:9}).toFile(asset(key));
  }
}

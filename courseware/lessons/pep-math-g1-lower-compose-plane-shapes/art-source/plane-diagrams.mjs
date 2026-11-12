import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require=createRequire(new URL('../../../../student-web/package.json',import.meta.url));
const sharp=require('sharp');
const asset=name=>fileURLToPath(new URL('../assets/'+name+'.png',import.meta.url));
const paper='#fcf0d3';
const ink='#2c5348';
const colors=['#7da88c','#efb16f','#8eb7c8','#d7897e','#c9bf78','#8aa9a3'];
const art={};
const pictures=new Map();
const rectangle=(x,y,w,h)=>[[x,y],[x+w,y],[x+w,y+h],[x,y+h]];
const place=(poly,x,y,unit)=>poly.map(([u,v])=>[x+u*unit,y+v*unit]);
const polygon=(poly,fill,edge=ink,width=3,extra='')=>
  '<polygon points="'+poly.map(p=>p.map(n=>Number(n.toFixed(3))).join(',')).join(' ')+
  '" fill="'+fill+'" stroke="'+edge+'" stroke-width="'+width+'" stroke-linejoin="round" '+extra+'/>';
const line=(x,y,xx,yy,fill=ink,width=4,dash='')=>
  '<path d="M'+x+' '+y+'L'+xx+' '+yy+'" stroke="'+fill+'" stroke-width="'+width+'" stroke-linecap="round" '+dash+'/>';
function arrow(x,y,xx,yy){
  const angle=Math.atan2(yy-y,xx-x);
  const tips=[angle-.55,angle+.55].map(a=>[xx-17*Math.cos(a),yy-17*Math.sin(a)]);
  return line(x,y,xx,yy)+polygon([[xx,yy],...tips],ink,ink,1);
}
const outline=poly=>polygon(poly,'none','#90462e',4.7,'stroke-dasharray="8 5"');
const pieces=(group,x,y,unit)=>group.map((poly,i)=>polygon(place(poly,x,y,unit),colors[i%colors.length])).join('');
function register(name,width,height,svg='',inputs=[]){
  art[name]=inputs;
  pictures.set(name,{width,height,svg});
}

const squarePair=[rectangle(0,0,1,1),rectangle(1,0,1,1)];
const touchPair=[rectangle(0,0,1,1),rectangle(1,1,1,1)];
const overlapPair=[rectangle(0,0,1,1),rectangle(.74,.20,1,1)];
const squareResult={outline:rectangle(0,0,2,1),parts:squarePair};
const fittedRectangles={outline:rectangle(0,0,2,2),parts:[rectangle(0,0,2,1),rectangle(0,1,2,1)]};
const longRectangles={outline:rectangle(0,0,4,1),parts:[rectangle(0,0,2,1),rectangle(2,0,2,1)]};
const narrowRectangles={outline:rectangle(0,0,3,2),parts:[rectangle(0,0,3,1),rectangle(0,1,3,1)]};
const diagonalSquare={
  outline:rectangle(0,0,2,2),
  parts:[[[0,0],[2,0],[2,2]],[[0,0],[2,2],[0,2]]],
};
const longTriangle={
  outline:[[0,2],[2,0],[4,2]],
  parts:[[[0,2],[2,0],[2,2]],[[2,0],[4,2],[2,2]]],
};
const slanted={
  outline:[[0,1.7],[3.1,1.7],[4.05,0],[.95,0]],
  parts:[[[0,1.7],[4.05,0],[.95,0]],[[0,1.7],[3.1,1.7],[4.05,0]]],
};
const H=Math.sqrt(3);
const largeTriangle={
  outline:[[0,2*H],[2,0],[4,2*H]],
  parts:[
    [[1,H],[2,0],[3,H]], [[0,2*H],[1,H],[2,2*H]],
    [[2,2*H],[3,H],[4,2*H]], [[1,H],[3,H],[2,2*H]],
  ],
};
const fourSquare={outline:rectangle(0,0,2,2),parts:Array.from({length:4},(_,i)=>rectangle(i%2,Math.floor(i/2),1,1))};
const fourRow={outline:rectangle(0,0,4,1),parts:Array.from({length:4},(_,i)=>rectangle(i,0,1,1))};
const sixRectangle={outline:rectangle(0,0,3,2),parts:Array.from({length:6},(_,i)=>rectangle(i%3,Math.floor(i/3),1,1))};

const samples={squareResult,fittedRectangles,longRectangles,narrowRectangles,diagonalSquare,longTriangle,slanted,
  largeTriangle,fourSquare,fourRow,sixRectangle};

register('edge-check',660,270,
  pieces(touchPair,41,59,58)+pieces(overlapPair,261,62,64)+pieces(squarePair,469,83,65)+
  line(534,83,534,148,'#fff3cf',6));
register('two-rectangles',610,308,
  pieces(longRectangles.parts,25,116,66)+arrow(303,150,351,150)+
  pieces(fittedRectangles.parts,389,78,78));
register('compare-rectangle-pairs',610,308,
  pieces(fittedRectangles.parts,62,60,85)+
  line(291,53,291,254,'#ad976f',3,'stroke-dasharray="6 7"')+
  pieces(narrowRectangles.parts,342,60,72));
register('triangles-two-ways',700,315,
  pieces(diagonalSquare.parts,47,75,78)+pieces(longTriangle.parts,274,75,91));
register('triangles-slanted',650,315,pieces(slanted.parts,69,54,123));
register('four-squares',660,290,
  pieces(fourRow.parts,43,116,63)+arrow(315,146,375,146)+pieces(fourSquare.parts,438,70,79));
register('more-pieces',680,340,
  pieces(largeTriangle.parts,37,30,75)+pieces(sixRectangle.parts,397,98,75));
register('fold-middle',650,325,
  pieces([rectangle(0,0,2.4,2.4)],46,58,82)+
  line(46+1.2*82,58,46+1.2*82,58+2.4*82,'#8a4127',6,'stroke-dasharray="11 7"')+
  arrow(273,156,329,156)+
  pieces([rectangle(0,0,1.2,2.4),rectangle(1.48,0,1.2,2.4)],365,58,82));
register('fold-diagonal',650,325,
  pieces([rectangle(0,0,2.4,2.4)],46,58,82)+
  line(46,58,46+2.4*82,58+2.4*82,'#8a4127',6,'stroke-dasharray="11 7"')+
  arrow(273,156,329,156)+
  pieces(diagonalSquare.parts,371,59,98.4));

const patchSets={
  narrow:{outline:rectangle(0,0,2,2),given:[rectangle(0,0,2,1)],patch:rectangle(0,1,2,1)},
  wide:{outline:rectangle(0,0,3.4,2),given:[rectangle(0,0,3.4,1)],patch:rectangle(0,1,3.4,1)},
  diag:{outline:diagonalSquare.outline,given:[diagonalSquare.parts[0]],patch:diagonalSquare.parts[1]},
  small:{outline:rectangle(0,0,1.45,1.45),given:[[[0,0],[1.45,0],[1.45,1.45]]],
    patch:[[0,0],[1.45,1.45],[0,1.45]]},
  slant:{outline:slanted.outline,given:[slanted.parts[0]],patch:slanted.parts[1]},
  equi:{outline:largeTriangle.outline,given:largeTriangle.parts.slice(0,3),patch:largeTriangle.parts[3]},
  peaked:{outline:longTriangle.outline,given:[longTriangle.parts[0]],patch:longTriangle.parts[1]},
};
for(const [key,set] of Object.entries(patchSets)){
  // A common scale makes a small paper triangle visibly smaller at the same zoom.
  const zoom=42, x=24, y=13;
  const patchMinX=Math.min(...set.patch.map(p=>p[0]));
  const patchMinY=Math.min(...set.patch.map(p=>p[1]));
  const patchView=set.patch.map(([a,b])=>[a-patchMinX,b-patchMinY]);
  const qwidth=Math.max(...patchView.map(p=>p[0]))*zoom,qheight=Math.max(...patchView.map(p=>p[1]))*zoom;
  register('piece-'+key,220,177,
    polygon(place(patchView,(220-qwidth)/2,(177-qheight)/2,zoom),colors[1],ink,4));
  register('gap-'+key,220,177,
    pieces(set.given,x,y,zoom)+outline(place(set.outline,x,y,zoom))+
    outline(place(set.patch,x,y,zoom)));
  register('filled-'+key,220,177,
    pieces([...set.given,set.patch],x,y,zoom));
}

function squareCard(name,svg){register(name,250,235,svg);}
squareCard('q-squares-aligned',pieces([rectangle(0,0,1,1),rectangle(0,1,1,1)],83,28,84));
squareCard('q-squares-corner',pieces(touchPair,42,39,84));
squareCard('q-squares-overlap',pieces([rectangle(0,0,1,1),rectangle(.22,.78,1,1)],73,38,87));
squareCard('q-rect-a',pieces([rectangle(0,0,2,1),rectangle(0,1.35,2,1)],60,36,65));
squareCard('q-rect-b',pieces([rectangle(0,0,2.5,1),rectangle(0,1.35,2.5,1)],46,36,65));
squareCard('q-rect-c',pieces([rectangle(0,0,3,1),rectangle(0,1.35,3,1)],27,36,65));

const quizTri={outline:rectangle(0,0,3,3),given:[[[0,0],[3,0],[0,3]]],patch:[[3,0],[3,3],[0,3]]};
squareCard('q-diag-plan',pieces(quizTri.given,50,43,51)+outline(place(quizTri.outline,50,43,51)));
squareCard('q-diag-fit',pieces([quizTri.patch],50,43,51));
squareCard('q-diag-small',pieces([[[2.1,0],[2.1,2.1],[0,2.1]]],71,54,51));
squareCard('q-diag-narrow',pieces([[[2.2,0],[2.2,3],[0,3]]],61,43,51));
squareCard('q-four-square',pieces(fourSquare.parts,44,36,79));
squareCard('q-four-line',pieces(fourRow.parts,21,90,52));
squareCard('q-four-step',pieces([rectangle(0,0,1,1),rectangle(1,0,1,1),rectangle(1,1,1,1),rectangle(2,1,1,1)],31,55,62));
squareCard('q-fold-plan',pieces([rectangle(0,0,2.5,2.5)],42,33,66)+line(42,198,207,33,'#8a4127',6,'stroke-dasharray="11 7"'));
squareCard('q-fold-triangles',pieces([[[0,0],[2.5,0],[2.5,2.5]],[[0,.20],[0,2.7],[2.5,2.7]]],38,48,66));
squareCard('q-fold-rectangles',pieces([rectangle(0,0,1,1.83),rectangle(1.27,0,1,1.83)],35,45,79));
squareCard('q-fold-squares',pieces([rectangle(0,0,1,1),rectangle(1.25,0,1,1)],35,75,79));

function half(x,y,r,side,color){
  const sweep=side==='left'?0:1;
  return '<path d="M'+x+' '+(y-r)+' A'+r+' '+r+' 0 0 '+sweep+' '+x+' '+(y+r)+
    ' Z" fill="'+color+'" stroke="'+ink+'" stroke-width="4" stroke-linejoin="round"/>';
}
squareCard('q-circle-plan',
  '<circle cx="125" cy="116" r="77" fill="none" stroke="#984828" stroke-width="5" stroke-dasharray="8 6"/>'+
  half(125,116,77,'left',colors[0]));
squareCard('q-circle-fit',half(91,116,77,'right',colors[1]));
squareCard('q-circle-small',half(91,116,53,'right',colors[1]));
squareCard('q-circle-rectangle',pieces([rectangle(0,0,1.5,3)],84,38,51));

register('bridge-preview',610,300,
  '<rect x="49" y="134" width="510" height="120" rx="16" fill="#709b88"/>'+
  pieces([rectangle(0,0,2,1)],263,51,41)+
  outline(place(rectangle(0,0,2,1),255,170,49))+
  outline(place(rectangle(0,0,2,2),413,147,44))+
  arrow(309,101,309,157));
register('marble-preview',610,300,'',['piece-narrow','gap-narrow','gap-wide']);
register('bench-scene',670,330,'',['greenhouse-table','two-designers']);
register('mosaic-scene',670,330,'',['family-collage','paper-flower']);

async function render(key,{width,height,svg}){
  const background='<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'">'+
    '<rect width="100%" height="100%" fill="'+paper+'"/>'+svg+'</svg>';
  const layers=[];
  const inputs=art[key];
  for(const [i,name] of inputs.entries()){
    const size=inputs.length===2?275:172;
    const left=inputs.length===2?34+i*327:34+i*190;
    const top=Math.round((height-size)/2);
    const image=await sharp(asset(name)).resize(size,size,{fit:'contain',background:paper}).png().toBuffer();
    layers.push({input:image,left,top});
  }
  await sharp(Buffer.from(background)).composite(layers).png().toFile(asset(key));
}

if(process.argv.includes('--describe'))console.log(JSON.stringify({art,samples,patchSets,quizTri}));
else for(const [key,data] of pictures)await render(key,data);

// Original Mira schoolbag. Deterministic authoring source; no downloaded models.
// Run with the project's Node: node scripts/build-schoolbag-model.mjs
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import * as T from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';

// GLTFExporter uses this browser API only to read the binary Blob in Node.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) { blob.arrayBuffer().then(value => { this.result = value; this.onloadend?.(); }); }
};
const scene = new T.Scene();
const bag = new T.Group(); bag.name = 'Backpack'; scene.add(bag);
const materials = {};
function material(name, color, roughness = .82, metalness = 0) {
  return materials[name] ??= new T.MeshStandardMaterial({ name, color, roughness, metalness });
}
const canvas = material('woven_ochre', '#dca747');
const piping = material('bound_edges', '#a87331');
const lining = material('cotton_lining', '#8c5935');
const pocket = material('pocket_canvas', '#e5b356');
const webbing = material('blue_webbing', '#527074');
const thread = material('linen_thread', '#ffe1a1');
const metal = material('brushed_brass', '#b99153', .35, .55);
const tag = material('cotton_label', '#f7f0d9');

function mesh(name, geometry, mat, parent, position = [0, 0, 0]) {
  const obj = new T.Mesh(geometry, mat); obj.name = name;
  obj.position.set(...position); obj.castShadow = true; obj.receiveShadow = true;
  parent.add(obj); return obj;
}
function box(name, size, position, mat, parent = bag, radius = .08) {
  return mesh(name, new RoundedBoxGeometry(...size, 3, radius), mat, parent, position);
}
function softPanel(width, length, thickness, radius) {
  const shape = new T.Shape(), x = -width / 2, y = -length / 2;
  shape.moveTo(x + radius,y); shape.lineTo(x + width-radius,y); shape.quadraticCurveTo(x+width,y,x+width,y+radius);
  shape.lineTo(x+width,y+length-radius); shape.quadraticCurveTo(x+width,y+length,x+width-radius,y+length);
  shape.lineTo(x+radius,y+length); shape.quadraticCurveTo(x,y+length,x,y+length-radius);
  shape.lineTo(x,y+radius); shape.quadraticCurveTo(x,y,x+radius,y);
  const geometry = new T.ExtrudeGeometry(shape,{depth:thickness,bevelEnabled:true,bevelSize:.035,bevelThickness:.035,bevelSegments:3,steps:1,curveSegments:8});
  geometry.translate(0,0,-thickness/2); geometry.rotateX(Math.PI/2); geometry.computeVertexNormals(); return geometry;
}
function curve(name, points, radius, mat, parent = bag, closed = false) {
  const path = new T.CatmullRomCurve3(points.map(p => new T.Vector3(...p)), closed);
  return mesh(name, new T.TubeGeometry(path, Math.max(20, points.length * 3), radius, 5, closed), mat, parent);
}
function stitch(name, points, parent = bag) {
  const path = new T.CatmullRomCurve3(points.map(p => new T.Vector3(...p)));
  const count = Math.ceil(path.getLength() * 16), pieces = [];
  for (let i = 0; i < count; i++) {
    const at = path.getPoint(i / count), direction = path.getTangent(i / count);
    const geometry = new T.CylinderGeometry(.007, .007, .032, 3);
    geometry.applyQuaternion(new T.Quaternion().setFromUnitVectors(new T.Vector3(0, 1, 0), direction));
    geometry.translate(at.x, at.y, at.z); pieces.push(geometry);
  }
  const merged = mergeGeometries(pieces); pieces.forEach(piece => piece.dispose());
  if (merged) mesh(name, merged, thread, parent);
}

// A hollow fabric shell: the opening, rim and inner wall are real geometry.
function ringPoint(angle, v, inner = false) {
  const c = Math.cos(angle), s = Math.sin(angle);
  const taper = .88 + .12 * Math.sin(v * Math.PI / 2) + .035 * Math.sin(v*Math.PI);
  const x = Math.sign(c) * Math.abs(c) ** .56 * 1.34 * taper;
  const z = Math.sign(s) * Math.abs(s) ** .7 * .61 * (.85 + .15 * v + .14 * Math.sin(v*Math.PI));
  const top = .94 - .20 * Math.max(0, s) ** 4;
  return [x * (inner ? .94 : 1), -1.48 + v * (top + 1.48), z * (inner ? .87 : 1)];
}
function shell(inner) {
  const vertices = [], indices = [], uvs = [], segments = 96, rows = 15;
  for (let y = 0; y <= rows; y++) for (let i = 0; i <= segments; i++) {
    vertices.push(...ringPoint(i / segments * Math.PI * 2, y / rows, inner));
    uvs.push(i / segments * 3, y / rows * 2);
  }
  for (let y = 0; y < rows; y++) for (let i = 0; i < segments; i++) {
    const a = y * (segments + 1) + i, b = a + segments + 1;
    indices.push(a, b, a + 1, b, b + 1, a + 1);
  }
  const geometry = new T.BufferGeometry();
  geometry.setAttribute('position', new T.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute('uv', new T.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices); geometry.computeVertexNormals();
  const mat = inner ? lining : canvas; mat.side = T.DoubleSide;
  return mesh(inner ? 'Interior' : 'FabricBody', geometry, mat, bag);
}
shell(false); shell(true);
box('SoftBase', [2.36, .27, 1.03], [0, -1.42, 0], canvas, bag, .13);
const rim = Array.from({ length: 96 }, (_, i) => ringPoint(i / 96 * Math.PI * 2, 1));
curve('RolledOpening', rim, .039, piping, bag, true);
const bottomSeam = Array.from({ length: 72 }, (_, i) => ringPoint(i / 72 * Math.PI * 2, .045));
curve('BaseBinding', bottomSeam, .025, piping, bag, true);
for (const sign of [-1, 1]) {
  curve(`RearStrap${sign}`, [[sign*.82,.8,-.58],[sign*1.02,.35,-.9],[sign*1.02,-.9,-.98],[sign*.78,-1.28,-.53]], .105, webbing);
  const side = box(`SidePocket${sign}`, [.27, .78, .8], [sign * 1.28, -.83, .08], pocket, bag, .12);
  side.rotation.z = sign * -.035;
  curve(`SideHem${sign}`, [[sign*1.32,-.47,-.22],[sign*1.43,-.45,.1],[sign*1.34,-.47,.39]], .025, piping);
}
curve('CarryHandle', [[-.42,.86,-.54],[-.43,1.44,-.56],[0,1.60,-.56],[.43,1.44,-.56],[.42,.86,-.54]], .068, webbing);

box('FrontPocket', [2.03, 1.05, .29], [0, -.69, .64], pocket, bag, .18);
curve('PocketBinding', [[-.84,-.19,.76],[-1,-.38,.74],[-.93,-1.12,.73],[0,-1.21,.78],[.93,-1.12,.73],[1,-.38,.74],[.84,-.19,.76]], .018, piping);
stitch('PocketStitch', [[-.82,-.24,.805],[-.91,-.4,.806],[-.86,-1.08,.804],[0,-1.14,.815],[.86,-1.08,.804],[.91,-.4,.806],[.82,-.24,.805]]);
curve('ZipperTape', [[-.87,-.21,.79],[0,-.19,.826],[.87,-.21,.79]], .041, webbing);
const teeth = [];
for (let i = 0; i < 42; i++) {
  const g = new T.BoxGeometry(.018,.028,.018); g.translate(-.81+i*.0395,-.19,.86); teeth.push(g);
}
mesh('ZipperTeeth', mergeGeometries(teeth), metal, bag); teeth.forEach(g => g.dispose());
const pull = box('ZipperPull', [.07,.24,.04], [.72,-.31,.86], material('coral_pull','#bc6654'), bag, .018); pull.rotation.z = -.28;
box('FrontLabel', [.55,.28,.025], [0,-.63,.801], tag, bag, .025);
// Small stitched emblem, deliberately not a face or a copied brand mark.
curve('LabelBookLeft', [[-.13,-.57,.822],[-.13,-.7,.822],[0,-.68,.822],[0,-.56,.822],[-.13,-.57,.822]], .008, webbing);
curve('LabelBookRight', [[0,-.56,.822],[.13,-.57,.822],[.13,-.7,.822],[0,-.68,.822]], .008, webbing);

const flap = new T.Group(); flap.name = 'FlapHinge'; flap.position.set(0, .96, -.53); bag.add(flap);
// The carry loop travels with the lid, so the lid never cuts through it.
flap.attach(bag.getObjectByName('CarryHandle'));
mesh('FlapOuter', softPanel(2.64,1.42,.09,.22), canvas, flap, [0,.035,.64]);
mesh('FlapLining', softPanel(2.43,1.23,.03,.2), lining, flap, [0,-.055,.65]);
box('FlapApron', [2.56,.43,.18], [0,-.14,1.29], canvas, flap, .08);
curve('FlapBoundEdge', [[-1.27,0,.14],[-1.29,0,1.11],[-1.1,-.28,1.37],[0,-.32,1.39],[1.1,-.28,1.37],[1.29,0,1.11],[1.27,0,.14]], .023, piping, flap);
stitch('FlapStitch', [[-1.19,.128,.16],[-1.2,.128,1.08],[0,.128,1.27],[1.2,.128,1.08],[1.19,.128,.16]], flap);
box('LatchRibbon', [.28,.51,.04], [0,-.17,1.402], webbing, flap, .019);
const clasp = mesh('BrassLatch', new T.CylinderGeometry(.09,.09,.025,20), metal, flap, [0,-.31,1.438]); clasp.rotation.x=Math.PI/2;

const bookLayout = JSON.parse(await readFile(new URL('../src/components/schoolbag/book-layout.json', import.meta.url), 'utf8'));
const subjects = bookLayout.map(book => book.subject);
const paper = material('ivory_pages','#fff6df',.96);
for (let i=0; i<subjects.length; i++) {
  const book = new T.Group(); book.name = `Book_${subjects[i]}`;
  const { rest, palette } = bookLayout[i];
  book.position.set(rest.x, rest.y, rest.z);
  book.rotation.z = rest.turn; book.scale.setScalar(.9); scene.add(book);
  const cover = material(`bookcloth_${subjects[i]}`, palette.color, .88);
  box(`Pages_${i}`, [.978,1.765,.14],[.018,0,0],paper,book,.016);
  box(`BackCover_${i}`,[1.065,1.89,.044],[0,0,-.097],cover,book,.02);
  box(`Spine_${i}`,[.064,1.89,.214],[-.512,0,0],cover,book,.03);
  // A cloth-bound joint, rounded boards, and folded end bands give the book
  // physical depth even when only its top half is visible above the bag.
  const gilt = material('book_foil','#bf9850',.43,.35);
  for (const y of [-.78,.78]) {
    box(`SpineBand_${i}_${y}`,[.066,.012,.216],[-.512,y,0],gilt,book,.003);
    curve(`Headband_${i}_${y}`, [[-.47,y/Math.abs(y)*.88,-.065],[-.44,y/Math.abs(y)*.897,0],[-.47,y/Math.abs(y)*.88,.065]],.009,cover,book);
  }
  const hinge = new T.Group(); hinge.name = `CoverHinge_${subjects[i]}`; hinge.position.set(-.52,0,.096); book.add(hinge);
  box(`Cover_${i}`,[1.065,1.89,.042],[.52,0,0],cover,hinge,.02);
  mesh(`CoverArt_${subjects[i]}`,new T.PlaneGeometry(.99,1.816),material(`art_${i}`,'#ffffff'),hinge,[.535,0,.023]);
  box(`CoverJoint_${i}`,[.015,1.82,.009],[.04,0,.022],cover,hinge,.004);
  const inside=mesh(`InsideArt_${subjects[i]}`,new T.PlaneGeometry(1.017,1.829),material(`inside_${i}`,'#fffaf0'),hinge,[.52,0,-.024]); inside.rotation.y=Math.PI;
  mesh(`PageArt_${subjects[i]}`,new T.PlaneGeometry(.94,1.72),material(`page_${i}`,'#fffaf0'),book,[.028,0,.074]);
  const edges=[];
  for(let j=0;j<18;j++){
    const z=-.064+j*.0075;
    const side=new T.BoxGeometry(.003,1.724,.0013);side.translate(.508,0,z);edges.push(side);
    for (const sign of [-1,1]) {const top=new T.BoxGeometry(.94,.0015,.0013);top.translate(.025,sign*.882,z);edges.push(top);}
  }
  mesh(`PageEdges_${i}`,mergeGeometries(edges),material('page_edges','#d5c9ad'),book);edges.forEach(g=>g.dispose());
  const ribbon = material(`ribbon_${i}`,['#d49d48','#d09569','#b45f49','#548b8b'][i],.9);
  curve(`Bookmark_${i}`,[[.29,.84,-.045],[.3,1.01,-.04],[.32,1.045,.025],[.335,.99,.066]],.025,ribbon,book);
}

scene.updateMatrixWorld(true);
const buffer = await new GLTFExporter().parseAsync(scene, {binary:true, onlyVisible:false});
const folder = new URL('../public/models/schoolbag/', import.meta.url);
await mkdir(folder,{recursive:true});
await writeFile(new URL('schoolbag-v5.glb',folder),Buffer.from(buffer));
let vertices=0,meshes=0;
scene.traverse(obj=>{if(obj.isMesh){meshes++;vertices+=obj.geometry.getAttribute('position').count;}});
await writeFile(new URL('asset-manifest.json',folder),JSON.stringify({version:5,author:'Mira original procedural model',source:'scripts/build-schoolbag-model.mjs',bytes:buffer.byteLength,meshes,vertices,subjects,parts:['Backpack','FlapHinge',...subjects.flatMap(subject=>[`Book_${subject}`,`CoverHinge_${subject}`])]},null,2)+'\n');
console.log(JSON.stringify({bytes:buffer.byteLength,meshes,vertices}));

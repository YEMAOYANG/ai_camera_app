import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { regroup,diagramProof } from '../art-source/bookmark-diagrams.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const template=fileURLToPath(new URL('../../../kit/game_templates/',import.meta.url));
const proof=diagramProof();
test('every supported operand pair conserves quantity in both orders',()=>{
  let integerCases=0;
  for(let original=10;original<=99;original++)for(let add=1;add<=9&&original+add<=100;add++){
    const m=regroup(original,add), swapped=regroup(add,original);
    assert.equal(m.total,original+add);
    assert.equal(m.total,10*(m.tens+m.carry)+m.left);
    assert.equal(m.loose,original%10+add);
    assert.equal(m.carry,Number(m.loose>=10));
    for(const k of ['whole','tens','old','added','loose','carry','left','total'])assert.equal(m[k],swapped[k]);
    integerCases++;
  }
  assert.equal(regroup(72,8).left,0);
  assert.equal(regroup(97,3).total,100);
  assert.equal(integerCases,774);
});

test('each diagram preserves its step quantity and every question has one correct pictured option',()=>{
  for(const x of Object.values(proof)){
    if(x.layout==='fill'){
      assert.equal(x.frameCount+x.outside,x.model.loose);
      assert.equal(x.frameCount,Math.min(x.model.loose,10));
    }
    if(x.layout==='exchange'){
      const left=x.left, sum=x.model?.loose??x.total;
      assert.equal(10*x.newTens+left,sum);
    }
    if(x.layout==='packed'&&x.model)assert.equal(x.quantity,x.model.total);
  }
  const quiz=JSON.parse(fs.readFileSync(root+'/lesson.json')).scenes.find(s=>s.type==='quiz');
  const correct=['b','a','c','b','a','c'];
  const expected=[62,15,72,60,83,73];
  quiz.questions.forEach((q,i)=>{
    assert.equal(q.answer[0],correct[i]);
    const chosen=proof[q.options[correct[i]].visual.image];
    assert.equal(chosen.model?.total??chosen.quantity,expected[i]);
    if(i===0){
      for(const [key,o] of Object.entries(q.options))assert.equal(proof[o.visual.image].model.carry,Number(key==='b'));
    }else for(const [key,o] of Object.entries(q.options))assert.equal(proof[o.visual.image].quantity===expected[i],key===correct[i]);
  });
});

function setup(file,page){
  const anchors={};
  const K={ready(){},$(){return {style:{}};},$$(){return [];},el(tag,className){return {tag,className,style:{}};},
    onState(){},game(data){this.built=data;return {follow(selector,position){anchors[selector]={...position()};}};}};
  class Image{constructor(){this.complete=true;this.naturalWidth=1;}}
  const vmc=vm.createContext({K,Image});
  vm.runInContext(fs.readFileSync(template+'classic.js','utf8'),vmc);
  const classic=vm.runInContext('Classic',vmc);
  classic.create=(cfg,model)=>({cfg,model});
  vm.runInContext(fs.readFileSync(template+file,'utf8'),vmc);
  vm.runInContext(fs.readFileSync(root+'/pages/'+page,'utf8'),vmc);
  return {...K.built,openingFallback:K.startPictureFallback(),anchors};
}
const idle={held:()=>false,press:()=>false};
const press=action=>({held:k=>k===action,press:k=>k===action});
const feedback=()=>({awards:0,losses:0,award(){this.awards++;},lost(){this.losses++;},
  move(){},drop(){},fx(){},resetCheckpoint(){}});
function run(built,custom){
  const {cfg,model}=built;
  let moves=0;
  cfg.levels.forEach((level,i)=>model.validate(level,i));
  for(let round=0;round<2;round++){
    cfg.levels.forEach((l,i)=>{
      const w=model.reset(l), fb=feedback();
      if(i===0)custom(built,w,l,fb,round);
      for(let frames=0;fb.awards<model.goal(l)&&frames<7000;frames++){
        model.update(w,l,model.pilot(w,l),.04,fb);
        moves++;
      }
      assert.equal(fb.awards,model.goal(l),round+' '+i);
    });
  }
  return moves;
}
const images=[];
const screen={drawImage(im){images.push(im.src);}};
test('落块 rejects a wrong drop and pairs actual loose quantities in both rounds',()=>{
  const tiles=setup('fallingTiles.js','pair-loose-bookmarks.js');
  run(tiles,(built,w,l,fb)=>{
    assert.equal(w.i,0);
    built.model.update(w,l,press('action'),.04,fb);
    assert.equal(fb.losses,1);
    assert.equal(fb.awards,0);
    built.drawTop({data:{level:l,progress:w.i}},screen);
    assert.equal(w.i,0);
    assert.equal(images.length,0);
    built.model.update(w,l,idle,.41,fb);
    built.model.update(w,l,press('left'),.04,fb);
    built.model.update(w,l,press('action'),.04,fb);
    assert.equal(fb.awards,1);
    built.drawTop({data:{level:l,progress:w.i}},screen);
    assert.equal(images.pop(),'__IMG:tile-proof-5-6__');
  });
  for(const level of tiles.cfg.levels){
    for(const next of level.pieces){
      const counts=level.bottom.filter(old=>old!==null&&level.matches(next,old));
      assert.equal(counts.length,1);
      const old=+counts[0].split('-')[1],added=+next.split('-')[1];
      assert.equal(old+added,level.total);
      assert.equal(proof['tile-proof-'+old+'-'+added].left,level.total-10);
    }
  }
});

test('推箱 rejects an incorrect total, retains the accepted result, and resets it on replay',()=>{
  const depot=setup('sortingDepot.js','deliver-regrouped-bookmarks.js');
  const demo=depot.cfg.levels[0];
  depot.model.validate(demo,0);
  const dw=depot.model.reset(demo),demoFeedback=feedback();
  for(let i=0;i<2000&&!demoFeedback.awards;i++)depot.model.update(dw,demo,depot.model.pilot(dw,demo),.04,demoFeedback);
  assert.equal(demoFeedback.awards,1);
  assert.equal(dw.state.items[0],-1-(4*8+3));
  run(depot,(built,w,l,fb)=>{
    function move(key){built.model.update(w,l,press(key),.35,fb);}
    move('right');
    assert.equal(fb.losses,1);
    assert.equal(fb.awards,0);
    assert.equal(w.wrongGroup,'dock-43');
    const wrongItems=[...w.state.items];
    images.length=0;
    built.drawTop({data:{w,level:l}},screen);
    assert.deepEqual(images,['__IMG:order-38-5__']);
    move('up');move('right');move('down');move('down');
    assert.equal(fb.awards,1);
    assert.notDeepEqual([...w.state.items],wrongItems);
    images.length=0;
    built.drawTop({data:{w,level:l}},screen);
    assert(images.includes('__IMG:packed-38-5__'));
    move('action');
    images.length=0;
    built.drawTop({data:{w,level:l}},screen);
    assert.deepEqual(images,['__IMG:order-38-5__']);
    assert(w.state.items.every(p=>p>=0));
    fb.awards=0; // classic clears this checkpoint count during the restart callback.
  });
  for(const l of depot.cfg.levels){
    for(const item of l.items){
      const [a,b]=item.token.split('-').map(Number);
      assert.equal(item.group,'dock-'+(a+b));
      assert.equal(l.docks.filter(d=>d.group===item.group).length,1);
      assert.equal(proof['packed-'+item.token].quantity,a+b);
    }
  }
});

test('formal game art is present and the original quantity card remains the opening fallback',()=>{
  const lesson=JSON.parse(fs.readFileSync(root+'/lesson.json'));
  for(const [template,page,readyKey] of [
    ['fallingTiles.js','pair-loose-bookmarks','tiles-ready'],
    ['sortingDepot.js','deliver-regrouped-bookmarks','depot-ready'],
  ]){
    const built=setup(template,page+'.js');
    const scene=lesson.scenes.find(item=>item.key===page);
    assert.notEqual(scene.startImage,readyKey);
    assert.equal(built.openingFallback.tag,'img');
    assert.equal(built.openingFallback.src,'__IMG:'+readyKey+'__');
    assert.ok(built.openingFallback.alt);
    const keyFor=asset=>asset.match(/^__IMG:([a-z0-9-]+)__$/)[1];
    const art=built.cfg.art;
    const keys=[scene.startImage,keyFor(art.backdrop),keyFor(art.sticker),...(art.frames??[]).map(keyFor)];
    for(const key of keys){
      const png=fs.readFileSync(root+'/'+lesson.images[key].file);
      assert.equal(png.subarray(1,4).toString('ascii'),'PNG');
    }
  }
});

test('the teacher highlights the canvas cards and keeps the same delivery order beside its result',()=>{
  const seen=[];
  const context={drawImage(image,...bounds){seen.push({src:image.src,bounds});}};
  const tiles=setup('fallingTiles.js','pair-loose-bookmarks.js');
  tiles.drawTop({data:{level:tiles.cfg.levels[0],progress:1}},context);
  assert.deepEqual(seen.splice(0),[{
    src:'__IMG:tile-proof-5-6__',bounds:Object.values(tiles.anchors['#tile-result']),
  }]);

  const depot=setup('sortingDepot.js','deliver-regrouped-bookmarks.js');
  const level=depot.cfg.levels[0];
  depot.model.validate(level,0);
  const world=depot.model.reset(level);
  const actions=feedback();
  for(let frame=0;frame<1000&&actions.awards===0;frame++){
    depot.model.update(world,level,depot.model.pilot(world,level),.04,actions);
  }
  assert.equal(actions.awards,1);
  depot.drawTop({autoLoop:true,data:{level,w:world}},context);
  assert.deepEqual(seen.splice(0),[
    {src:'__IMG:order-38-5__',bounds:Object.values(depot.anchors['#depot-order'])},
    {src:'__IMG:packed-38-5__',bounds:Object.values(depot.anchors['#depot-result'])},
  ]);
  depot.drawTop({autoLoop:false,data:{level,w:world}},context);
  assert.equal(seen[0].src,'__IMG:order-47-6__');
});


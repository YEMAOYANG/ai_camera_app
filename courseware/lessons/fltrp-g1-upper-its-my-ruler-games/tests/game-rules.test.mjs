import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function load(file) {
  let options;
  const button={hidden:true,addEventListener(){}};
  vm.runInNewContext(fs.readFileSync(new URL(`../pages/${file}.js`,import.meta.url),'utf8'),{
    K:{
      ready(){},
      game(value){options=value;},
      sfx:{pick(){},coin(){}},
      draw:{},
    },
    Image:class{},
    document:{getElementById:()=>button},
  },{filename:file+'.js'});
  return {options,button};
}

function simulation(file,level,{auto=false,demo=false}={}) {
  const {options}=load(file),hints=[];
  const g={
    level,auto,autoLoop:demo,pointer:{x:640,y:525,active:false},keys:{},
    win(){this.wins++;},wins:0,miss(){this.misses++;},misses:0,
    say(text,kind){if(kind==='no') hints.push(text);},
    sparkle(){},
  };
  options.reset(g,level);
  return {
    g,hints,
    point(x,y){g.pointer={x,y,active:true};},
    tick(seconds,steer) {
      for(let i=0;i<Math.ceil(seconds*60)&&!g.wins;i++){
        if(steer)steer(g);
        if(g.auto)options.autopilot(g,1/60);
        options.update(g,1/60);
      }
    },
  };
}

for(const page of ['return-the-stationery','paint-the-parade']){
  test(page+' finishes every configured level with the normal motion solver',()=>{
    for(let level=0;level<3;level++){
      const sim=simulation(page,level,{auto:true});
      sim.tick(45);
      assert.equal(sim.g.wins,1,`unreachable level ${level+1}`);
      assert.equal(sim.g.data.index,sim.g.data.rounds.length-1);
    }
  });
  test(page+' has a different teacher example and a fresh first child round',()=>{
    const demo=simulation(page,0,{auto:true,demo:true});
    const handoff=simulation(page,0);
    assert.notDeepEqual(demo.g.data.rounds,handoff.g.data.rounds);
    assert.equal(handoff.g.data.index,0);
    assert.equal(handoff.g.misses,0);
  });
  test(page+' leaves the reset button hidden across demonstration loops',()=>{
    const {options,button}=load(page);
    const g={level:0,auto:true,autoLoop:true,pointer:{active:true}};
    options.reset(g,0);
    assert.equal(button.hidden,true);
    options.reset(g,0);
    assert.equal(button.hidden,true);
    g.auto=false;g.autoLoop=false;
    g.pointer.active=true;
    options.reset(g,0);
    assert.equal(button.hidden,false);
    assert.equal(g.pointer.active,false);
  });
}

test('delivery keeps the parcel on a wrong window and gives a reason to look again',()=>{
  const sim=simulation('return-the-stationery',0);
  sim.point(392,598);sim.tick(1);
  assert.equal(sim.g.data.cargo,null);
  assert.match(sim.hints[0],/发话牌/);
  assert.doesNotMatch(sim.hints[0],/尺/);
  sim.point(888,598);sim.tick(1.4);
  assert.equal(sim.g.data.cargo,'ruler');
  sim.point(392,275);sim.tick(1.65);
  assert.equal(sim.g.data.cargo,'ruler');
  assert.equal(sim.g.wins,0);
  assert.match(sim.hints[1],/是谁/);
  sim.point(888,275);sim.tick(3);
  assert.equal(sim.g.wins,1);
  assert.equal(sim.g.data.delivered,'ruler');
  assert.equal(sim.g.data.cargo,null);
});

test('roller uses the selected paint and needs sustained contact with the correct item',()=>{
  const sim=simulation('paint-the-parade',0);
  sim.point(400,617);sim.tick(0.85);
  assert.equal(sim.g.data.ink,'red');
  const target=g=>g.data.cards.find(c=>c.key==='pencil');
  const follow=g=>{
    const {x}=target(g);
    sim.point(x>1128||x<138?770:x-20,x>1128||x<138?522:382);
  };
  sim.tick(17,follow);
  assert.match(sim.hints[0],/颜色/);
  assert.equal(target(sim.g).coverage,0);
  sim.point(640,617);sim.tick(1.7);
  assert.equal(sim.g.data.ink,'yellow');
  sim.tick(20,follow);
  assert.equal(sim.g.wins,1);
  assert.equal(target(sim.g).coverage,1);
  assert.equal(sim.g.data.brush.y,525);
});

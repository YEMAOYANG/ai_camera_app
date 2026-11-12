const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

const templates = path.join(__dirname, '../../../kit/game_templates');
const pages = path.join(__dirname, '../pages');
const source = file => fs.readFileSync(file, 'utf8');
const frame = 1 / 60;

function load(template, page) {
  let result;
  const K = {ready(){}, $(){return {style:{}};}, game(){return {follow(){}};}};
  const context = {K, Image:class {}, record(config, rules){result={config, rules};}};
  const classic = source(path.join(templates,'classic.js'));
  const capture = 'Classic.create = (config,rules) => { record(config,rules); return {draw(){}}; };';
  vm.runInNewContext([classic, capture, source(path.join(templates,template+'.js')),
    source(path.join(pages,page+'.js'))].join('\n'), context);
  result.config.levels.forEach(result.rules.validate);
  return result;
}

function drive(rules, level, world, until, onAward) {
  const quiet=()=>{};
  const feedback={fx:quiet,move:quiet,jump:quiet,drop:quiet,lost:quiet,award:onAward};
  for(let t=0;t<5400&&!until();t++){
    rules.update(world,level,rules.pilot(world,level,frame),frame,feedback);
  }
  assert.ok(until(),'the real movement and collision rules must reach the expected state');
}

test('hop routes land on the known group, then the derived group, then their total',()=>{
  const {config,rules}=load('platformHop','jump-to-the-linked-counts');
  const comparisons=[[8,-3],[9,4],[20,6]];
  for(const [index,level] of config.levels.entries()){
    const [known,change]=comparisons[index];
    const needed=[known,known+change,known+known+change];
    const world=rules.reset(level);
    const landed=[];
    drive(rules,level,world,()=>landed.length===3,()=>landed.push(world.checkpoint[3]));
    assert.deepEqual(landed,needed);
  }
});

test('delivery preserves the actual first answer in the cargo until the second answer is delivered',()=>{
  const {config,rules}=load('listenDelivery','deliver-the-intermediate-result');
  const expected=[[10,22],[23,39],[25,19]];
  for(const [index,level] of config.levels.entries()){
    const [first,second]=expected[index];
    const world=rules.reset(level);
    const phases=[];
    drive(rules,level,world,()=>phases.length===2,()=>{
      phases.push([world.carried,world.delivered.get('station-'+second)]);
    });
    assert.deepEqual(phases,[['parcel-'+first,undefined],[null,'parcel-'+first]]);
  }
});

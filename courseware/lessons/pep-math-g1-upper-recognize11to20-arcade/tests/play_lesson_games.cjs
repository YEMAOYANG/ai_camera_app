// Test the authored math games through real browser events. The local HTML
// files are produced with build.prepare and autoplay.page_html before running.
const assert = require('node:assert/strict');
const { join } = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(join(process.env.PW_DIR, 'node_modules/playwright-core'));
const [folder, chrome] = process.argv.slice(2);

async function fixture(browser, game) {
  const page = await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  const errors=[];
  page.on('pageerror', error=>errors.push(String(error)));
  await page.clock.install();
  await page.goto(pathToFileURL(join(folder,`${game}.html`)).href);
  const advance=ms=>page.clock.runFor(ms);
  const snapshot=()=>page.evaluate(()=>{
    const {progress,total,w,failures}=K.game.current.data;
    return {...K.game.status(),progress,total,failures,checkpoint:w?.checkpoint?.[3],
      slow:w?.failureCount,errors:K.errs.slice()};
  });
  const screenshot=state=>process.env.MIRA_VISUAL_REVIEW==='1' ?
    page.screenshot({path:join(folder,`${game}-${state}.png`)}) : Promise.resolve();
  const set=async state=>{
    await page.evaluate(state=>window.postMessage({type:'SET_WIDGET_STATE',state},'*'),state);
    await advance(34);
  };
  const keys=async (key,time)=>{
    await page.keyboard.down(key);await advance(time);await page.keyboard.up(key);
  };
  const widths=()=>page.locator('.arc-key:visible').evaluateAll(nodes=>nodes.map(n=>{
    const r=n.getBoundingClientRect();return [r.width,r.height];
  }));
  const demo=async ms=>{
    await set({demo:true,level:1,pause:true});await advance(1800);
    assert.equal((await snapshot()).progress,0,'initial board stays still during the teacher question');
    await set({demo:true,pause:false});await advance(ms);
  };
  const assertNoErrors=async()=>{
    assert.deepEqual((await snapshot()).errors,[],`${game} frame errors`);
    assert.deepEqual(errors,[],`${game} browser errors`);
  };
  return {page,advance,snapshot,screenshot,set,keys,widths,demo,assertNoErrors};
}

async function pack(browser) {
  const f=await fixture(browser,'packing');
  const {page,advance,snapshot,screenshot,set,keys,widths,demo,assertNoErrors}=f;
  try {
    await screenshot('ready');
    await demo(550);
    assert.equal((await snapshot()).progress,1);
    await screenshot('demo');
    await set({demo:false,level:1,pause:false});
    assert.equal((await snapshot()).progress,0);
    assert.ok((await widths()).every(pair=>pair.every(size=>size>=44)));
    for(let attempt=1;attempt<=2;attempt++) {
      await keys('ArrowRight',285); // Six rods are now beside seven and two.
      await keys('Space',34);
      assert.equal((await snapshot()).misses,attempt);
      assert.equal((await snapshot()).progress,0);
      if(attempt===1)await screenshot('hint');
      await advance(540);
    }
    assert.equal((await snapshot()).slow,2);
    // At spawn, move to the only column beside four rods and use the touch action.
    await keys('ArrowLeft',34);
    await page.locator('[data-arc-input="action"]').tap();
    await advance(90);
    assert.equal((await snapshot()).progress,1);
    assert.equal(await page.locator('#bundle-crate').getAttribute('data-bundles'),'1');
    assert.equal(await page.evaluate(()=>K.game.current.bubbleObj?.kind==='no'),false);
    await screenshot('success');
    await assertNoErrors();
  } finally {await page.close();}
}

async function touchHop(page, advance, direction, ms) {
  const session=await page.context().newCDPSession(page);
  const boxes=await Promise.all([direction,'action'].map(key=>page.locator(`[data-arc-input="${key}"]`).boundingBox()));
  await session.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:boxes.map((box,id)=>({
    x:box.x+box.width/2,y:box.y+box.height/2,id,
  }))});
  await advance(ms);
  await session.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await session.detach();
}

async function track(browser) {
  const f=await fixture(browser,'number-track');
  const {page,advance,snapshot,screenshot,set,keys,widths,demo,assertNoErrors}=f;
  const hop=async (key,ms)=>{
    await page.keyboard.down(key);
    await keys('Space',33);await advance(ms-33);
    await page.keyboard.up(key);
    await advance(950-ms);
  };
  try {
    await screenshot('ready');
    await demo(780);
    await screenshot('demo');
    await set({demo:false,level:1,pause:false});
    assert.equal((await snapshot()).checkpoint,'start');
    assert.ok((await widths()).every(pair=>pair.every(size=>size>=44)));
    // Capture the rendered direction token, not the internal answer state.
    await page.evaluate(()=>{
      const draw=K.draw.text;
      K.draw.text=(c,s,x,y,...rest)=>{if(x===640&&y===46)window.hudPrompt=s;return draw(c,s,x,y,...rest);};
    });
    await advance(34);
    assert.equal(await page.evaluate(()=>window.hudPrompt),'+1');
    await hop('ArrowLeft',571);
    assert.equal((await snapshot()).misses,1);
    assert.equal((await snapshot()).progress,0);
    await screenshot('hint');
    await advance(510);
    await touchHop(page,advance,'right',571);
    await advance(400);
    assert.equal((await snapshot()).checkpoint,12);
    await screenshot('success');
    for(const expected of [13,14]) {
      await hop('ArrowRight',571);
      assert.equal((await snapshot()).checkpoint,expected);
    }
    await advance(1500);await page.locator('#g-next').tap();await advance(34);
    assert.equal(await page.evaluate(()=>window.hudPrompt),'−1');
    for(const expected of [16,15,14,13]) {
      await hop('ArrowLeft',518);
      assert.equal((await snapshot()).checkpoint,expected);
    }
    await advance(1500);await page.locator('#g-next').tap();await advance(34);
    assert.equal(await page.evaluate(()=>window.hudPrompt),'↔');
    await screenshot('challenge');
    await hop('ArrowRight',466); // 14→18 is longer, so the wrong direction cannot score.
    assert.equal((await snapshot()).progress,0);
    await advance(510);
    for(const expected of [13,12,11]) {
      await hop('ArrowLeft',466);
      assert.equal((await snapshot()).checkpoint,expected);
    }
    await advance(1500);
    assert.equal((await snapshot()).state,'done');
    assert.deepEqual((await snapshot()).stars,[3,3,3]);
    await assertNoErrors();
  } finally {await page.close();}
}

(async()=>{
  const browser=await chromium.launch({executablePath:chrome});
  try {
    await pack(browser);
    await track(browser);
    console.log('Math arcade: two wrong drops recover, touch makes one bundle, and three number routes clear via actual input.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

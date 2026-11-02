/* Injected only into a SHA-bound Autumn scene. Client-reported actions are not mastery. */
(function () {
  'use strict';
  function install(sceneId) {
    if (!/^scene-p(?:8|9|10|11|12)$/.test(sceneId)) throw new Error('unsupported_scene');
    const d = document, listeners = [];
    const on = (type, fn) => { d.addEventListener(type, fn, true); listeners.push([type, fn]); };
    const bridge = () => window.miraCourseOperation;
    let stopped = false, dragging = null, writing = null;
    const fail = (reason) => {
      stopped = true;
      window.dispatchEvent(new CustomEvent('mira-course-operation-error', {detail:{reason}}));
    };
    const ready = e => {
      if (!e.isTrusted) return false;
      if (!stopped && bridge()?.ready === true && typeof bridge()?.send === 'function') return true;
      e.preventDefault(); e.stopImmediatePropagation();
      return false;
    };
    const send = op => {
      if (stopped || bridge()?.ready !== true) return fail('not_ready');
      try { Promise.resolve(bridge().send(op)).catch(() => fail('send_failed')); }
      catch (_) { fail('send_failed'); }
    };
    const node = e => e.target instanceof Element ? e.target : null;
    const closest = (e, selector) => node(e)?.closest(selector);
    const id = (e, value) => !!closest(e, '#'+value);
    const afterStart = () => {
      if (sceneId === 'scene-p8') return d.getElementById('startOverlay')?.classList.contains('hidden');
      if (sceneId === 'scene-p9' || sceneId === 'scene-p11') return d.getElementById('start')?.hidden === true;
      if (sceneId === 'scene-p10') return d.getElementById('ready-layer')?.hidden === true;
      return d.getElementById('start-overlay')?.classList.contains('hidden');
    };
    const currentChar = () => d.querySelector('.char-choice[aria-pressed="true"]')?.getAttribute('data-char');
    const goosePosition = g => ({name:'move',bird:Number(g.dataset.gooseId),x:parseFloat(g.style.left)*1024/100,y:parseFloat(g.style.top)*576/100});
    const objectPosition = g => ({name:'move',index:Number(g.dataset.index),x:parseFloat(g.style.left),y:parseFloat(g.style.top)});
    const snapMove = (item, fn) => queueMicrotask(() => {
      if (!item?.isConnected) return fail('move_target_lost');
      const op = fn(item);
      if (!Number.isFinite(op.x) || !Number.isFinite(op.y)) return fail('invalid_position');
      send(op);
    });
    const activate = e => {
      const el = node(e); if (!el) return;
      if (sceneId === 'scene-p8') {
        if (id(e,'startGooseBtn') && !afterStart()) return send({name:'start'});
        if (!afterStart()) return;
        if (id(e,'btnLeader')) {
          const selected=d.querySelector('.goose.selected'); if (!selected) return fail('leader_missing');
          return send({name:'leader',bird:Number(selected.dataset.gooseId)});
        }
        for (const [key,name] of [['btnDirection','rotate'],['btnOrder','reverseOrder'],['btnReset','reset'],['btnTest','submit'],['btnReplay','hint'],['btnRetryAudio','hint']])
          if (id(e,key)) { if(key==='btnOrder' && d.getElementById(key)?.disabled) return; return send({name}); }
      }
      if (sceneId === 'scene-p9') {
        if (id(e,'startBtn') && !afterStart()) return send({name:'start'});
        if (!afterStart()) return;
        const context=closest(e,'[data-context]'), tone=closest(e,'[data-tone]');
        if (context) return send({name:'context',index:Number(context.dataset.context)});
        if (tone) {
          if ((d.getElementById('progress')?.textContent || '').replace(/\s/g,'')==='4/4') return;
          return send({name:'choose',tone:Number(tone.dataset.tone)});
        }
        for (const [key,name] of [['try','submit'],['next','next'],['reset','reset'],['hint','hint'],['replay','hint']])
          if (id(e,key)) { if(d.getElementById(key)?.disabled || d.getElementById(key)?.hidden) return; return send({name}); }
      }
      if (sceneId === 'scene-p10') {
        if (id(e,'start-pencil') && !afterStart()) return send({name:'start'});
        if (!afterStart()) return;
        const choice=closest(e,'.char-choice[data-char]');
        if (choice) return send({name:'character',character:choice.dataset.char});
        for (const [key,name] of [['btn-undo','undo'],['btn-retry','retry'],['btn-center','hint'],['btn-demo','hint'],['btn-replay-error','hint']])
          if (id(e,key)) { if(d.getElementById(key)?.hidden) return; return send({name}); }
      }
      if (sceneId === 'scene-p11') {
        if (id(e,'startBtn') && !afterStart()) return send({name:'start'});
        if (!afterStart()) return;
        const mode=closest(e,'[data-mode]'), example=closest(e,'[data-speak]'), text=closest(e,'[data-example]');
        if (mode) return send({name:'mode',index:Number(mode.dataset.mode)});
        if (example) return send({name:'example',index:Number(example.dataset.speak)});
        if (text) { if(d.getElementById('supportLabel')?.textContent==='自己尝试') return send({name:'restoreText'}); return; }
        for (const [key,name] of [['hide','hide'],['restore','restore'],['save','save'],['next','next'],['retry','retry'],['replay','hint']])
          if (id(e,key)) { if(d.getElementById(key)?.disabled || d.getElementById(key)?.hidden) return; return send({name}); }
      }
      if (sceneId === 'scene-p12') {
        if (id(e,'start-book') && !afterStart()) return send({name:'start'});
        if (!afterStart()) return;
        const object=closest(e,'.window-card[data-object]'); if(object) return send({name:'object',object:object.dataset.object});
        const delta=closest(e,'[data-delta]'); if(delta) return send({name:'quantity',delta:Number(delta.dataset.delta)});
        for (const key of ['color','direction','action']) {
          const value=closest(e,'[data-'+key+']'); if(value) return send({name:key,[key]:value.dataset[key]});
        }
        for (const [key,name] of [['btn-compare-a','b'],['btn-compare-b','a']]) if(id(e,key)) return send({name:'page',page:name});
        if (id(e,'btn-save-version-a') || id(e,'btn-save-version-b')) return send({name:'save'});
        for (const [key,name] of [['btn-undo','undo'],['btn-reset','reset'],['btn-replay','hint'],['retry-audio-btn','hint']]) if(id(e,key)) return send({name});
      }
    };
    on('click', e => { if (!ready(e)) return; activate(e); });
    on('keydown', e => {
      if (!ready(e)) return;
      const g=sceneId==='scene-p8' ? closest(e,'.goose[data-goose-id]') : sceneId==='scene-p12' ? closest(e,'.obj-icon[data-index]') : null;
      if (g && afterStart() && ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) {
        const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
        const op=sceneId==='scene-p8'?goosePosition(g):objectPosition(g), step=sceneId==='scene-p8'?12:3;
        const bounds=sceneId==='scene-p8'?[[45,979],[55,521]]:[[10,90],[14,86]];
        op.x=Math.max(bounds[0][0],Math.min(bounds[0][1],op.x+delta[0]*step));
        op.y=Math.max(bounds[1][0],Math.min(bounds[1][1],op.y+delta[1]*step));
        if (!Number.isFinite(op.x)||!Number.isFinite(op.y)) return fail('invalid_position');
        return send(op);
      }
      if ((e.key==='Enter'||e.key===' ') && node(e)?.closest('[role="button"]:not(button)')) activate(e);
    });
    on('pointerdown', e => {
      if (!ready(e) || !afterStart()) return;
      if (sceneId==='scene-p10' && id(e,'writing-canvas')) {
        const box=d.getElementById('writing-canvas').getBoundingClientRect();
        if (!box.width || !box.height) return fail('canvas_unavailable');
        const point=ev=>({x:Math.max(0,Math.min(1,(ev.clientX-box.left)/box.width)),y:Math.max(0,Math.min(1,(ev.clientY-box.top)/box.height))});
        writing={pointerId:e.pointerId,character:currentChar(),point,points:[point(e)]};
      } else {
        const g=sceneId==='scene-p8'?closest(e,'.goose[data-goose-id]'):sceneId==='scene-p12'?closest(e,'.obj-icon[data-index]'):null;
        if(g) dragging={pointerId:e.pointerId,element:g};
      }
    });
    on('pointermove', e => {
      if (!e.isTrusted || !writing || e.pointerId!==writing.pointerId) return;
      if (!ready(e)) return;
      if(writing.points.length>=256) { e.preventDefault(); e.stopImmediatePropagation(); writing=null; return fail('stroke_too_many_points'); }
      writing.points.push(writing.point(e));
    });
    on('pointerup', e => {
      if (!e.isTrusted) return;
      if (!ready(e)) { writing=null; dragging=null; return; }
      if (writing && e.pointerId===writing.pointerId) {
        const w=writing; writing=null;
        if(w.points.length>1) send({name:'stroke',character:w.character,points:w.points});
      }
      if (dragging && e.pointerId===dragging.pointerId) {
        const g=dragging.element;dragging=null;snapMove(g,sceneId==='scene-p8'?goosePosition:objectPosition);
      }
    });
    on('pointerleave', e => {
      if (e.isTrusted && writing && e.pointerId===writing.pointerId && id(e,'writing-canvas')) writing=null;
    });
    on('pointercancel', e => {
      if (!e.isTrusted) return;
      writing=null;
      if(dragging && e.pointerId===dragging.pointerId) {
        if (!ready(e)) { dragging=null; return; }
        const g=dragging.element;dragging=null;snapMove(g,sceneId==='scene-p8'?goosePosition:objectPosition);
      }
    });
    // Only compare immutable server evidence with the restored display.
    // Other pages remain blocked on non-initial states until fully verified.
    const restore = server => {
      try {
        if (!server || typeof server.phase !== 'string' || typeof server.completed !== 'boolean' || typeof window.miraActivityCheckpoint?.capture !== 'function') return false;
        const snap=window.miraActivityCheckpoint.capture(), domain=snap?.domainState;
        if (!domain) return false;
        if (sceneId==='scene-p9') {
          if (!Array.isArray(domain.completedContexts) || !Array.isArray(server.completedContexts)) return false;
          return domain.context===server.context && domain.selectedTone===server.tone &&
            JSON.stringify([...domain.completedContexts].sort())===JSON.stringify([...server.completedContexts].sort()) &&
            (snap.feedbackPhase==='ready')===(server.phase==='ready') &&
            (snap.feedbackPhase==='level_complete')===server.completed;
        }
        if (sceneId==='scene-p11') {
          if (!Array.isArray(domain.practiceSaved) || domain.practiceSaved.length!==3 || !Array.isArray(server.saved)
              || !Array.isArray(domain.supports) || !Array.isArray(server.supports)) return false;
          return domain.mode===server.mode && JSON.stringify(domain.supports)===JSON.stringify(server.supports) &&
            JSON.stringify(domain.practiceSaved.map((saved,i)=>saved?i:null).filter(i=>i!==null))===JSON.stringify([...server.saved].sort()) &&
            (snap.feedbackPhase==='ready')===(server.phase==='ready') &&
            (snap.feedbackPhase==='level_complete')===server.completed;
        }
        if (sceneId==='scene-p10') {
          const child=snap.childDecision, versions=server.versions;
          if (!child || !versions || !Array.isArray(child.completedChars) || !Array.isArray(server.completedChars)
              || !Array.isArray(server.strokes) || !Array.isArray(versions.ren) || !Array.isArray(versions.da)) return false;
          const normalized = strokes => {
            if (!Array.isArray(strokes)) return null;
            return strokes.map(stroke => {
              if (!Array.isArray(stroke)) return null;
              const sampled=stroke.length<=256 ? stroke : Array.from({length:256},(_,i)=>stroke[Math.round(i*(stroke.length-1)/255)]);
              return sampled.map(p=>Array.isArray(p)?p:[p?.x,p?.y]);
            });
          };
          return child.currentChar===server.character &&
            JSON.stringify(normalized(child.versionA))===JSON.stringify(normalized(versions.ren)) &&
            JSON.stringify(normalized(child.versionB))===JSON.stringify(normalized(versions.da)) &&
            JSON.stringify(normalized(child.currentVersion))===JSON.stringify(normalized(server.strokes)) &&
            JSON.stringify([...child.completedChars].sort())===JSON.stringify([...server.completedChars].sort()) &&
            (domain.phase==='ready')===(server.phase==='ready') &&
            (child.completedChars.length===2)===server.completed;
        }
        if (sceneId==='scene-p8') {
          // Inline percent coordinates round when read back from CSS; 0.01px
          // accommodates serialization, not a materially different position.
          const near=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<0.01;
          const positions=(geese,expected)=>Array.isArray(geese)&&geese.length===7&&Array.isArray(expected)&&expected.length===7&&
            geese.every((g,i)=>g?.id===i && Array.isArray(expected[i]) && expected[i].length===2 && near(g.x,expected[i][0]) && near(g.y,expected[i][1]));
          if (!Array.isArray(domain.previousLegs) || !Array.isArray(server.previousLegs) ||
              domain.previousLegs.length!==server.previousLegs.length ||
              !domain.previousLegs.every((leg,i)=>leg.level===i+1 && leg.formationType===server.previousLegs[i]?.formation &&
                leg.leaderId===server.previousLegs[i]?.leader && positions(leg.positions,server.previousLegs[i]?.positions))) return false;
          return domain.started===(server.phase!=='ready') && domain.level===server.level &&
            domain.flightAngle===server.flightAngle && domain.leaderId===server.leader &&
            JSON.stringify(domain.order)===JSON.stringify(server.order) && positions(domain.geese,server.positions) &&
            domain.geese.every(g=>g.directionAngle===domain.flightAngle && !!g.isLeader===(g.id===domain.leaderId)) &&
            (domain.phase==='level_complete')===server.completed;
        }
        if (sceneId==='scene-p12') {
          const content=value=> {
            if (!value || typeof value!=='object' || !Array.isArray(value.positions)) return null;
            return {selectedObject:value.selectedObject,color:value.color,quantity:value.quantity,direction:value.direction,
              action:value.action,positions:value.positions.map(p=>({x:p.x,y:p.y}))};
          };
          const equal=(a,b)=> {
            if (!a || !b || !Array.isArray(a.positions) || !Array.isArray(b.positions) ||
                a.positions.length!==b.positions.length) return false;
            for (const key of ['selectedObject','color','quantity','direction','action']) if (a[key]!==b[key]) return false;
            return a.positions.every((p,i)=>Number.isFinite(p.x) && Number.isFinite(p.y) &&
              Number.isFinite(b.positions[i]?.x) && Number.isFinite(b.positions[i]?.y) &&
              Math.abs(p.x-b.positions[i].x)<0.0001 && Math.abs(p.y-b.positions[i].y)<0.0001);
          };
          if (!domain.drafts || !domain.versions || !server.drafts || !server.versions ||
              !Array.isArray(domain.revisionHistory) || !Array.isArray(server.history)) return false;
          for (const key of ['a','b']) {
            if (!content(domain.drafts[key]) || !equal(content(domain.drafts[key]),content(server.drafts[key]))) return false;
            const own=domain.versions[key]?.childDecision ?? null, stored=server.versions[key] ?? null;
            if ((own===null)!==(stored===null) || (own!==null && !equal(content(own),content(stored)))) return false;
          }
          if (domain.revisionHistory.length!==server.history.length ||
              !domain.revisionHistory.every((entry,i)=>entry.version===server.history[i]?.page &&
                equal(content(entry.before),content(server.history[i]?.before)))) return false;
          const pageFlipAfterCompletion=server.completed && domain.feedbackPhase==='revise_or_retry' &&
            server.versions.a!==null && server.versions.b!==null && !equal(content(server.versions.a),content(server.versions.b));
          return domain.started===(server.phase!=='ready') && domain.currentVersionPage===server.page &&
            ((domain.feedbackPhase==='level_complete')===server.completed || pageFlipAfterCompletion);
        }
        return false;
      } catch (_) { return false; }
    };
    const onRestore = e => {
      if (e.detail?.sceneId!==sceneId) return;
      const ok=restore(e.detail.serverState);
      if (typeof bridge()?.restoreConfirmed==='function') bridge().restoreConfirmed(ok);
    };
    window.addEventListener('mira-course-operation-restore',onRestore);
    return {
      restore,
      dispose() { for (const [type,fn] of listeners) d.removeEventListener(type,fn,true); window.removeEventListener('mira-course-operation-restore',onRestore); stopped=true; },
    };
  }
  window.installAutumnCourseAdapter = install;
})();

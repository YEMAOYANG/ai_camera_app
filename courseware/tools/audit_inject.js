(function () {
  const errors = window.__miraAuditErrors || [], problems = [], missingTargets = [];

  function hidden(el) {
    for (let node = el; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (node.classList.contains('nocheck') || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) < 0.05) return true;
    }
    return false;
  }
  function desc(el) { return el.id ? '#' + el.id : el.tagName.toLowerCase(); }
  function audit() {
    const stage = document.querySelector('#cv') || document.documentElement;
    const sr = stage.getBoundingClientRect();
    const sx = stage.id === 'cv' ? sr.width / 1280 : innerWidth / 1280;
    const sy = stage.id === 'cv' ? sr.height / 720 : innerHeight / 720;
    if (!sx || !sy) { problems.push('Stage has zero size'); return; }
    const originX = stage.id === 'cv' ? sr.left : 0, originY = stage.id === 'cv' ? sr.top : 0;
    function box(r) { return {x0:(r.left-originX)/sx, y0:(r.top-originY)/sy, x1:(r.right-originX)/sx, y1:(r.bottom-originY)/sy}; }
    function outside(r) { return r.x0 < -1 || r.y0 < -1 || r.x1 > 1281 || r.y1 > 721; }
    let overlay = null;
    const centre = document.elementFromPoint(originX + 640 * sx, originY + 360 * sy);
    for (let el = centre; el && el !== stage && el !== document.body && el !== document.documentElement; el = el.parentElement) {
      const r = box(el.getBoundingClientRect());
      const width = Math.max(0, Math.min(1280, r.x1) - Math.max(0, r.x0));
      const height = Math.max(0, Math.min(720, r.y1) - Math.max(0, r.y0));
      if (width * height >= 1280 * 720 * 0.85) overlay = el;
    }
    const texts = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const el = node.parentElement;
      if (!node.nodeValue.trim() || !el || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(el.tagName) || hidden(el) || (overlay && !overlay.contains(el))) continue;
      const range = document.createRange(); range.selectNodeContents(node);
      for (const rect of range.getClientRects()) {
        if (rect.width < 1 || rect.height < 1) continue;
        const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
        if (top && !el.contains(top) && !top.contains(el)) continue;
        const r = box(rect), inset = (r.y1-r.y0)*0.15;
        r.y0 += inset; r.y1 -= inset;
        const label = node.nodeValue.trim().slice(0, 30);
        texts.push({el, r, label});
        if (outside(r)) problems.push('Text outside stage: ' + label);
        for (let parent = el; parent && parent !== stage; parent = parent.parentElement) {
          const style = getComputedStyle(parent);
          if (style.overflowX !== 'visible' || style.overflowY !== 'visible') {
            const p = box(parent.getBoundingClientRect());
            if (r.x0 < p.x0-1.5 || r.y0 < p.y0-1.5 || r.x1 > p.x1+1.5 || r.y1 > p.y1+1.5) { problems.push('Text clipped: ' + label + ' in ' + desc(parent)); break; }
          }
        }
      }
    }
    for (let i = 0; i < texts.length; i++) for (let j = i+1; j < texts.length; j++) {
      const a = texts[i], b = texts[j];
      if (a.el === b.el) continue;
      const x = Math.min(a.r.x1,b.r.x1)-Math.max(a.r.x0,b.r.x0), y = Math.min(a.r.y1,b.r.y1)-Math.max(a.r.y0,b.r.y0);
      const area = Math.min((a.r.x1-a.r.x0)*(a.r.y1-a.r.y0), (b.r.x1-b.r.x0)*(b.r.y1-b.r.y0));
      if (x > 2 && y > 2 && x*y > area*0.2) problems.push('Text overlap: ' + a.label + ' / ' + b.label);
    }
    const clickableSelector = 'button,a[href],[role="button"],input,select,[onclick]';
    document.querySelectorAll('*').forEach(el => {
      if (hidden(el) || el.disabled || (overlay && !overlay.contains(el)) || getComputedStyle(el).pointerEvents === 'none' || !(el.matches(clickableSelector) || getComputedStyle(el).cursor === 'pointer')) return;
      for (let parent = el.parentElement; parent; parent = parent.parentElement) {
        if (parent.matches(clickableSelector) || getComputedStyle(parent).cursor === 'pointer') return;
      }
      const rect = el.getBoundingClientRect(), r = box(rect);
      if (!rect.width || !rect.height) return;
      if (outside(r)) problems.push('Clickable outside stage: ' + desc(el));
      if (r.x1-r.x0 < 44 || r.y1-r.y0 < 44) problems.push('Clickable too small: ' + desc(el));
      const top = document.elementFromPoint(rect.left+rect.width/2, rect.top+rect.height/2);
      if (top && !el.contains(top) && !top.contains(el)) problems.push('Clickable covered: ' + desc(el) + ' by ' + desc(top));
    });
  }
  window.addEventListener('message', event => {
    if (event.source !== parent || !event.data) return;
    const message = event.data;
    if (['HIGHLIGHT_ELEMENT', 'ANNOTATE_ELEMENT', 'REVEAL_ELEMENT'].includes(message.type)) {
      try { if (!message.target || !document.querySelector(message.target)) missingTargets.push(String(message.target)); }
      catch (error) { missingTargets.push(String(message.target)); }
    }
    if (message.type === 'MIRA_AUDIT_CHECK' || message.type === 'MIRA_AUDIT_FINISH') {
      try { audit(); } catch (error) { errors.push('audit: ' + String(error)); }
      if (message.type === 'MIRA_AUDIT_FINISH') parent.postMessage({type:'MIRA_AUDIT_RESULT', result:{errors, problems:[...new Set(problems)], missingTargets}}, '*');
    }
  }, true);
})();

/* Shared configuration, art primitives and input for real-time mechanics.
 * Visuals are target text/numbers, {count:n}, {grid:{filled,total,columns}},
 * or {image:registeredImageUrl, fallback:visual} with a meaningful fallback.
 * Quantity diagrams may use a six-digit hex color or {groups:[visual,...]}.
 */
K.gameTemplates = (function () {
  const colors = {
    ink: '#244147', paper: '#FFFCF3', line: '#BCDBD8', accent: '#127B76',
    mint: '#C6EFE4', sky: '#E0F2FA', blue: '#65ADC5', earth: '#D7AE74',
    amber: '#FFD18C', green: '#328A65', white: '#FFFFFF'
  };
  const images = new Map();
  const templates = {};

  function assert(condition, message) {
    if (!condition) throw new Error('game template: ' + message);
  }

  function integer(n, min, max) {
    return Number.isInteger(n) && n >= min && n <= max;
  }

  function clamp(n, min, max) {
    return Math.min(max, Math.max(min, n));
  }

  function distance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function move(point, target, speed, dt) {
    const gap = distance(point, target);
    if (gap === 0) return;
    const step = Math.min(1, speed * dt / gap);
    point.x += (target.x - point.x) * step;
    point.y += (target.y - point.y) * step;
  }

  function box(c, x, y, w, h, fill, radius = 18, stroke) {
    K.draw.rr(c, x, y, w, h, radius);
    c.fillStyle = fill;
    c.fill();
    if (stroke) {
      c.strokeStyle = stroke;
      c.lineWidth = 3;
      c.stroke();
    }
  }

  function circle(c, x, y, radius, fill) {
    c.fillStyle = fill;
    K.draw.circle(c, x, y, radius);
  }

  function line(c, a, b, color, width = 5) {
    c.beginPath();
    c.moveTo(a.x, a.y);
    c.lineTo(b.x, b.y);
    c.lineCap = 'round';
    c.lineWidth = width;
    c.strokeStyle = color;
    c.stroke();
  }

  function text(c, value, x, y, size, maxWidth, fill = colors.ink) {
    c.font = '800 ' + size + 'px ' + K.FONT;
    const width = c.measureText(String(value)).width;
    K.draw.text(c, String(value), x, y, Math.max(12, Math.min(size, size * maxWidth / Math.max(width, 1))), fill);
  }

  function validateVisual(value) {
    if ((typeof value === 'string' && value.trim()) || Number.isFinite(value)) return;
    assert(value && typeof value === 'object' && !Array.isArray(value), 'a visual is missing');
    assert(value.color == null || /^#[0-9a-f]{6}$/i.test(value.color), 'invalid visual color');
    if (value.groups) {
      assert(Array.isArray(value.groups) && integer(value.groups.length, 2, 4), 'need 2–4 visual groups');
      value.groups.forEach(validateVisual);
    } else if (value.image) {
      assert(typeof value.image === 'string', 'image must be a registered image URL');
      validateVisual(value.fallback);
      if (!images.has(value.image)) {
        const img = new Image();
        img.src = value.image;
        images.set(value.image, img);
      }
    } else if (value.grid) {
      const {filled, total, columns} = value.grid;
      assert(integer(total, 1, 24) && integer(filled, 0, total) && integer(columns, 1, total), 'invalid quantity grid');
    } else {
      assert(integer(value.count, 0, 24), 'invalid visual count');
    }
  }

  function visual(c, value, x, y, w, h) {
    if (typeof value !== 'object') {
      text(c, value, x, y, Math.min(53, h * 0.8), w - 8);
      return;
    }
    if (value.groups) {
      const slot = w / value.groups.length;
      value.groups.forEach((group, i) => {
        visual(c, group, x - w / 2 + slot * (i + 0.5), y, slot - 20, h);
        if (i) line(c, {x: x - w / 2 + slot * i, y: y - h * 0.33},
          {x: x - w / 2 + slot * i, y: y + h * 0.33}, colors.line, 4);
      });
      return;
    }
    if (value.image) {
      const img = images.get(value.image);
      if (img.complete && img.naturalWidth) {
        const scale = Math.min(w / img.naturalWidth, h / img.naturalHeight);
        const width = img.naturalWidth * scale;
        const height = img.naturalHeight * scale;
        c.drawImage(img, x - width / 2, y - height / 2, width, height);
      } else {
        visual(c, value.fallback, x, y, w, h);
      }
      return;
    }
    const grid = value.grid;
    const total = grid ? grid.total : value.count;
    if (total === 0) {
      text(c, 0, x, y, h * 0.55, w);
      return;
    }
    const columns = grid ? grid.columns : Math.min(5, total);
    const rows = Math.ceil(total / columns);
    const unit = Math.min(w / columns, h / rows);
    for (let i = 0; i < total; i++) {
      const px = x + (i % columns - (columns - 1) / 2) * unit;
      const py = y + (Math.floor(i / columns) - (rows - 1) / 2) * unit;
      if (grid) box(c, px - unit / 2, py - unit / 2, unit, unit, colors.white, 0, colors.line);
      if (!grid || i < grid.filled) circle(c, px, py, unit * 0.27, value.color || colors.accent);
    }
  }

  function world(c, fill, floor, y = 640) {
    c.fillStyle = fill;
    c.fillRect(0, 0, 1280, 720);
    if (floor) {
      c.fillStyle = floor;
      c.fillRect(0, y, 1280, 720 - y);
    }
  }

  function token(c, value, p, w = 112, h = 96, fill = colors.paper) {
    box(c, p.x - w / 2, p.y - h / 2, w, h, fill, 24, colors.line);
    visual(c, value, p.x, p.y, w - 14, h - 12);
  }

  function area(x, y, w = 104, h = w) {
    return {x: x - w / 2, y: y - h / 2, w, h};
  }

  function getInput(g) {
    return g.auto ? g.data.autoInput : g.data?.manualInput || g;
  }

  // The autopilot controls exactly the same pointer and key representation as a child.
  // It cannot advance a round, change positions, or resolve collisions.
  function point(g, x, y, down = false, tap = false) {
    const input = g.data.autoInput;
    Object.assign(input.pointer, {x, y, down, active: true});
    if (tap) input.taps.push({x, y});
  }

  function pressed(g) {
    return getInput(g).taps.length > 0;
  }

  function axis(g, direction) {
    const keys = getInput(g).keys;
    return direction === 'x' ? Number(!!keys.right) - Number(!!keys.left)
      : Number(!!keys.down) - Number(!!keys.up);
  }

  function options(round, min, max, field = 'options') {
    const values = round[field];
    assert(Array.isArray(values) && integer(values.length, min, max), field + ' must have ' + min + '–' + max + ' visuals');
    values.forEach(validateVisual);
  }

  function indices(values, length, field) {
    assert(Array.isArray(values) && values.length && new Set(values).size === values.length &&
      values.every(i => integer(i, 0, length - 1)), 'invalid ' + field + ' indices');
  }

  function answer(round) {
    assert(integer(round.answer, 0, round.options.length - 1), 'invalid answer index');
  }

  function hint(g, time = 2) {
    const d = g.data;
    if (g.bubbleObj && g.bubbleObj.kind === 'no' && g.bubbleObj.t < 0.4) return;
    const r = d.plan.rounds[d.round];
    g.miss();
    g.say(d.wrong++ === 0 ? r.hint : r.hint2, 'no', time);
  }

  function success(g, p) {
    if (g.data.next > 0) return;
    const r = g.data.plan.rounds[g.data.round];
    g.sparkle(p.x, p.y);
    K.sfx.coin();
    g.say(r.success || '做到了！', 'ok', 1.1);
    g.data.next = 0.85;
    if (!g.demoAction?.()) g.awardPoint?.();
  }

  function hud(g, c, goalHeight, guided) {
    const d = g.data;
    if (!d.plan) return;
    const dots = g.levels;
    box(c, 24, 24, 36 * dots + 28, 66, colors.paper, 30);
    for (let i = 0; i < dots; i++) circle(c, 56 + 36 * i, 57, i === g.level ? 12 : 9,
      i <= g.level ? colors.accent : colors.line);
    const total = d.plan.rounds.length;
    box(c, 24, 101, 130, 50, colors.paper, 23);
    text(c, (d.round + 1) + ' / ' + total, 89, 126, 30, 126);
    box(c, 322, 24, 636, goalHeight + 21, colors.paper, 29, colors.line);
    visual(c, d.plan.rounds[d.round].goal, 640, 34 + goalHeight / 2, 608, goalHeight);
    if (guided) {
      box(c, 24, 161, 178, 43, colors.paper, 18);
      text(c, g.score.total + ' / ×' + g.score.combo, 113, 182, 28, 164);
      return;
    }
    circle(c, 1200, 71, 48, colors.paper);
    c.beginPath();
    c.arc(1200, 71, 22, -0.9, 4.4);
    c.strokeStyle = colors.accent;
    c.lineWidth = 6;
    c.stroke();
    c.beginPath();
    c.moveTo(1200, 43);
    c.lineTo(1223, 48);
    c.lineTo(1218, 69);
    c.closePath();
    c.fillStyle = colors.accent;
    c.fill();
  }

  function freshInput() {
    return {pointer: {x: 640, y: 360, down: false, active: false}, taps: [], keys: {}};
  }

  function screenPad(g, controls) {
    const pad = K.el('div', 'g-template-pad', null, K.stage());
    const keys = new Map(), taps = new Set();
    const buttons = controls.map(([key, symbol, label]) => {
      const button = K.el('button', 'btn', null, pad);
      button.type = 'button';
      button.textContent = symbol;
      button.setAttribute('aria-label', label);
      button.dataset.gameNativeSpace = '';
      button.addEventListener('pointerdown', event => {
        if (button.disabled || g.inputBlocked() || g.state !== 'play') return;
        event.preventDefault();
        g.pointer.active = false;
        button.setPointerCapture(event.pointerId);
        if (key !== 'action') keys.set(event.pointerId, key);
        taps.add(key);
      });
      for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        button.addEventListener(type, event => keys.delete(event.pointerId));
      }
      button.addEventListener('click', event => {
        if (!event.detail && !button.disabled && !g.inputBlocked() && g.state === 'play') taps.add(key);
      });
      return button;
    });
    const clear = () => { keys.clear(); taps.clear(); };
    window.addEventListener('blur', clear);
    return {
      clear,
      read() {
        const input = {pointer: g.pointer, keys: {...g.keys}, taps: g.taps.slice()};
        for (const key of [...keys.values(), ...taps]) {
          if (key === 'action') input.taps.push({key: true});
          else input.keys[key] = true;
        }
        taps.clear();
        return input;
      },
      show() {
        const blocked = g.inputBlocked();
        if (blocked) clear();
        pad.hidden = g.state !== 'play' || g.auto;
        buttons.forEach(button => { button.disabled = blocked; });
      },
    };
  }

  function register(name, mechanic) {
    templates[name] = function (config) {
      assert(config && Array.isArray(config.levels) && integer(config.levels.length, 2, 3), 'need 2–3 levels');
      const levels = config.levels;
      const goalHeight = config.goalHeight ?? 84;
      const guided = config.narration != null && mechanic.controls != null;
      let pad;
      assert(integer(goalHeight, 84, 132), 'goalHeight must be 84–132');
      for (const level of levels) {
        assert(typeof level.name === 'string' && level.name.trim(), 'level name is missing');
        assert(Array.isArray(level.rounds) && integer(level.rounds.length, 1, 12), 'need 1–12 rounds per level');
        assert(level.demoRounds == null || (Array.isArray(level.demoRounds) &&
          integer(level.demoRounds.length, 1, 12)), 'demoRounds needs 1–12 rounds');
        for (const round of [...level.rounds, ...(level.demoRounds || [])]) {
          assert(round && typeof round.hint === 'string' && round.hint.trim() &&
            typeof round.hint2 === 'string' && round.hint2.trim() &&
            round.hint !== round.hint2 && [round.hint, round.hint2].every(s => [...s].length <= 30),
          'need different first and second hints of at most 30 characters');
          assert(round.success == null || (typeof round.success === 'string' && [...round.success].length <= 30),
            'success feedback must fit its bubble');
          validateVisual(round.goal);
          mechanic.validate(round);
        }
      }

      function startRound(g) {
        const d = g.data;
        d.wrong = 0;
        d.next = 0;
        g.bubbleObj = null;
        d.autoInput = freshInput();
        d.world = mechanic.reset(d.plan.rounds[d.round], g.level, d.round);
      }

      return {
        levels: levels.length,
        doneText: config.doneText,
        finishMark: config.finishMark || '★★★',
        demoOnce: guided,
        narration: guided ? config.narration : undefined,
        score: guided,
        starsFor: guided ? undefined : () => 3,
        winPause: 0.8,
        setup(g) {
          if (!K.$('#tip')) K.el('div', '', null, K.stage()).id = 'tip';
          if (guided) {
            pad = screenPad(g, mechanic.controls);
            const card = K.$('#ready .card');
            const start = card && K.$('button', card);
            if (start) {
              const route = K.el('div', 'g-template-map');
              route.setAttribute('aria-label', levels.length + ' 关');
              for (const _ of levels) K.el('i', '', null, route);
              card.insertBefore(route, start);
            }
          }
          K.startPictureFallback = () => {
            const canvas = K.el('canvas', 'pic');
            canvas.width = 560;
            canvas.height = 315;
            const ctx = canvas.getContext('2d');
            box(ctx, 0, 0, 560, 315, colors.sky, 0);
            visual(ctx, levels[0].rounds[0].goal, 280, 157, 470, 245);
            return canvas;
          };
          g.follow('#game-goal', () => area(640, 34 + goalHeight / 2, 636, goalHeight + 21));
          for (const role of ['player', 'target']) {
            g.follow('#game-' + role, () => g.data.world ? mechanic[role](g.data.world) : null);
          }
        },
        reset(g, level) {
          pad?.clear();
          const plan = levels[level];
          const rounds = g.auto && g.autoLoop && plan.demoRounds ? plan.demoRounds : plan.rounds;
          g.data = {plan: {rounds}, round: 0};
          startRound(g);
        },
        autopilot(g, dt) {
          const d = g.data;
          d.autoInput.taps = [];
          if (!d.next) mechanic.pilot(g, d.world, d.plan.rounds[d.round], dt);
        },
        update(g, dt) {
          const d = g.data;
          if (pad && !g.auto) d.manualInput = pad.read();
          if (!guided && getInput(g).taps.some(t => !t.key && Math.hypot(t.x - 1200, t.y - 71) <= 48)) {
            g.start(g.level);
            return;
          }
          if (d.next > 0) {
            d.next -= dt;
            if (d.next > 0) return;
            if (d.round === d.plan.rounds.length - 1) {
              g.win();
            } else {
              d.round++;
              startRound(g);
            }
            return;
          }
          mechanic.update(g, d.world, d.plan.rounds[d.round], dt);
        },
        draw(g, c) {
          pad?.show();
          const d = g.data;
          if (!d.world) return;
          mechanic.draw(g, c, d.world, d.plan.rounds[d.round]);
          hud(g, c, goalHeight, guided);
        },
        bubbleAt: () => ({x: 640, y: goalHeight + 91})
      };
    };
  }

  const helpers = {colors, assert, integer, clamp, distance, move, box, circle, line, text,
    validateVisual, visual, world, token, area, getInput, point, pressed, axis,
    options, indices, answer, hint, success, register};
  Object.defineProperty(templates, 'tools', {value: helpers});
  return templates;
})();

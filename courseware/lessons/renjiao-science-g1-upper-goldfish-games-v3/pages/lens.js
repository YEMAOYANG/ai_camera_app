/* Float a camera outside the aquarium. Move and hold it on each anatomical region. */
(function () {
  const D = K.draw;
  const box = (c, x, y, w, h, r, color) => {
    D.rr(c, x, y, w, h, r);
    c.fillStyle = color;
    c.fill();
  };
  const pen = {
    ink: '#153944', navy: '#173a51', teal: '#087970', green: '#39ad8e',
    blue: '#d7eeee', warm: '#f4af5c', paper: '#fffcf4'
  };
  const photos = [
    {name: '头', clue: '找有口和眼的一端', art: '__IMG:eye__'},
    {name: '躯干', clue: '找覆着鳞片的中段', art: '__IMG:scales__'},
    {name: '尾', clue: '找末端的大尾鳍', art: '__IMG:tail__'}
  ];
  const species = {
    orange: {art: '__IMG:fish-orange__', spots: [[.21, .49], [.49, .49], [.79, .53]]},
    white: {art: '__IMG:fish-white__', spots: [[.22, .48], [.49, .49], [.77, .51]]},
    carp: {art: '__IMG:fish-carp__', spots: [[.155, .515], [.49, .49], [.845, .48]]}
  };
  const levels = [
    {fish: 'orange', name: '给金鱼拍一组', w: 622, r: 65, first: true},
    {fish: 'white', name: '它会换方向', w: 600, sway: 65, speed: .52, start: 0, r: 60},
    {fish: 'carp', name: '换成鲤鱼也会找', w: 570, sway: 91, speed: .74, start: .15, r: 55}
  ];
  const scene = {x: 31, y: 148, w: 853, h: 519};
  const album = {x: 908, y: 148, w: 340, h: 519};
  const scale = 9 / 16;
  const exposure = .50;
  const limit = (n, low, high) => Math.min(high, Math.max(low, n));
  const drawText = (c, txt, x, y, size, color = pen.ink, align = 'left') =>
    D.text(c, txt, x, y, size, color, {align});
  function load(src) {
    const img = new Image();
    img.src = src;
    return img;
  }
  function ready(img) { return img.complete && img.naturalWidth > 0; }
  for (const item of photos) item.image = load(item.art);
  for (const item of Object.values(species)) item.image = load(item.art);

  function swim(level, time) {
    if (level.first) return {
      x: 493 - 82 * (1 - Math.exp(-time * .19)),
      y: 395 + Math.sin(time * .63) * 11,
      facingRight: false, w: level.w, h: level.w * scale
    };
    const t = time * level.speed + level.start;
    const direction = Math.cos(t);
    const profile = Math.min(1, .43 + 2.85 * Math.abs(direction));
    return {
      x: 458 + Math.sin(t) * level.sway,
      y: 395 + Math.sin(t * .68) * (level.sway * .25 + 10),
      facingRight: direction > 0,
      w: level.w * profile, h: level.w * scale,
      turning: profile < .78
    };
  }
  function target(part, sample, subject) {
    const [x, y] = subject.spots[part];
    return {
      x: sample.x + (x - .5) * sample.w * (sample.facingRight ? -1 : 1),
      y: sample.y + (y - .5) * sample.h
    };
  }
  function resolveSpecies(level) {
    const subject = species[level.fish];
    return ready(subject.image) ? subject :
      [species.orange, species.white, species.carp].find(other => ready(other.image)) || subject;
  }
  function boxImage(c, img, x, y, w, h) {
    if (!ready(img)) return;
    c.save();
    D.rr(c, x, y, w, h, 15);
    c.clip();
    const side = Math.min(img.naturalWidth, img.naturalHeight);
    c.drawImage(img, (img.naturalWidth - side) / 2, (img.naturalHeight - side) / 2, side, side, x, y, w, h);
    c.restore();
  }
  function drawFish(c, img, fish, panX = fish.x, panY = fish.y, zoom = 1) {
    if (!ready(img)) return;
    c.save();
    c.translate(panX, panY);
    c.scale((fish.facingRight ? -1 : 1) * zoom, zoom);
    c.globalCompositeOperation = 'multiply';
    c.drawImage(img, -fish.w / 2, -fish.h / 2, fish.w, fish.h);
    c.restore();
  }
  function focusFrame(c, x, y, r, color, progress) {
    c.strokeStyle = '#ffffff';
    c.lineWidth = 13;
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.stroke();
    c.strokeStyle = color;
    c.lineWidth = 7;
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.stroke();
    c.fillStyle = color;
    c.fillRect(x - 11, y - 2, 22, 4);
    c.fillRect(x - 2, y - 11, 4, 22);
    if (progress > 0) {
      c.strokeStyle = pen.green;
      c.lineWidth = 12;
      c.beginPath();
      c.arc(x, y, r + 10, -Math.PI / 2, progress * 2 * Math.PI - Math.PI / 2);
      c.stroke();
    }
  }
  function touchGuide(c, x, y, time) {
    c.save();
    c.translate(x + Math.sin(time * 3) * 12, y);
    c.lineCap = 'round';
    c.strokeStyle = '#ffffff';
    c.lineWidth = 9;
    c.fillStyle = '#fff4dc';
    c.beginPath();
    c.moveTo(9, 51);
    c.lineTo(0, 34);
    c.quadraticCurveTo(-5, 24, 3, 21);
    c.quadraticCurveTo(9, 18, 15, 26);
    c.lineTo(15, 1);
    c.quadraticCurveTo(17, -10, 25, -4);
    c.lineTo(26, 20);
    c.quadraticCurveTo(49, 16, 48, 37);
    c.lineTo(39, 55);
    c.closePath();
    c.stroke();
    c.fill();
    c.strokeStyle = pen.navy;
    c.lineWidth = 4;
    c.stroke();
    c.strokeStyle = pen.teal;
    c.beginPath();
    c.moveTo(-20, 4); c.lineTo(-58, -36); c.lineTo(-56, -17);
    c.moveTo(-58, -36); c.lineTo(-39, -34);
    c.stroke();
    c.restore();
  }
  function snapshot(c, stamp, x, y, w, h) {
    const mark = target(stamp.part, stamp.fish, stamp.subject);
    c.save();
    D.rr(c, x, y, w, h, 14);
    c.clip();
    c.fillStyle = '#ebf9f4';
    c.fillRect(x, y, w, h);
    const zoom = .81;
    drawFish(c, stamp.subject.image, stamp.fish,
      x + w / 2 + (stamp.fish.x - mark.x) * zoom,
      y + h / 2 + (stamp.fish.y - mark.y) * zoom, zoom);
    c.restore();
  }
  function gallery(c, d) {
    box(c, album.x, album.y, album.w, album.h, 26, pen.paper);
    drawText(c, '我的观察册', 934, 182, 33);
    drawText(c, d.shots.length + ' / 3', 1223, 182, 28, pen.teal, 'right');
    for (let i = 0; i < 3; i++) {
      const y = 212 + 142 * i;
      const shot = d.shots[i];
      const current = d.shots.length === i;
      box(c, 928, y, 299, 128, 20, shot ? '#d4efdf' : current ? '#d5efed' : '#f1ebdd');
      if (shot) snapshot(c, shot, 940, y + 13, 126, 101);
      else {
        c.save();
        c.globalAlpha = current ? 1 : .47;
        boxImage(c, photos[i].image, 940, y + 13, 126, 101);
        c.restore();
      }
      drawText(c, photos[i].name, 1085, y + 45, 34);
      drawText(c, shot ? '已拍到' : current ? '轮到这一张' : '等一等', 1086, y + 87, 21, pen.teal);
    }
  }
  function draw(g, c) {
    const d = g.data.album;
    if (!d) return;
    const subject = resolveSpecies(d.level);
    const fish = swim(d.level, d.time);
    const current = photos[d.shots.length];
    c.fillStyle = '#e5f5f1';
    c.fillRect(0, 0, 1280, 720);
    box(c, 32, 25, 1216, 96, 25, '#153e53');
    drawText(c, '给游鱼拍三张照片', 58, 59, 36, '#ffffff');
    drawText(c, '按住拖动 · 对准停一停', 61, 97, 21, '#bfe5de');
    drawText(c, '观察员  ' + (g.level + 1) + ' / 3', 1209, 73, 27, '#effaf4', 'right');

    c.save();
    D.rr(c, scene.x, scene.y, scene.w, scene.h, 28);
    c.clip();
    const water = c.createLinearGradient(0, scene.y, 0, 670);
    water.addColorStop(0, '#edfafa');
    water.addColorStop(1, '#c8e9eb');
    c.fillStyle = water;
    c.fillRect(scene.x, scene.y, scene.w, scene.h);
    for (let i = 0; i < 8; i++) {
      const y = 613 - ((d.time * (9 + i % 3) + i * 53) % 350);
      c.fillStyle = '#ffffff91';
      D.circle(c, 105 + 96 * i, y, 3 + i % 4);
    }
    box(c, 55, 170, 429, 57, 21, '#ffffffdf');
    drawText(c, current ? (fish.turning ? '它在转身，等一等' : current.clue) : '从头到尾拍全了！', 73, 198, 29);
    drawFish(c, subject.image, fish);

    if (current) {
      const {x, y} = d.camera;
      c.save();
      c.beginPath();
      c.arc(x, y, 55, 0, Math.PI * 2);
      c.clip();
      c.fillStyle = '#f0fffa';
      c.fillRect(x - 55, y - 55, 110, 110);
      const zoom = 1.38;
      drawFish(c, subject.image, fish, x + (fish.x - x) * zoom, y + (fish.y - y) * zoom, zoom);
      c.restore();
      focusFrame(c, x, y, 55, d.held ? pen.teal : pen.navy, d.focus / exposure);
      if (d.shots.length === 0 && !d.used && !g.auto) touchGuide(c, x + 34, y + 21, d.time);
    }
    if (d.flash > 0) {
      c.fillStyle = 'rgba(255,255,255,' + (d.flash * 1.8) + ')';
      c.fillRect(scene.x, scene.y, scene.w, scene.h);
    }
    c.restore();
    gallery(c, d);
  }

  K.ready({title: '给游鱼拍三张照片', sub: '把相机拖到鱼身上。对准停一停，照片就进观察册。'});
  K.game({
    levels: levels.length,
    winPause: 1.18,
    bannerTime: .85,
    finishMark: '★★★',
    doneTitle: '观察册拍满了',
    doneText: '先找口和眼，再找鳞片，最后找尾鳍。',
    winText: () => '口和眼、鳞片、尾鳍，都在右边的观察册里。',
    starsFor: () => 3,
    levelName: index => levels[index].name,
    bubbleAt: () => ({x: 446, y: 593}),
    setup(g) {
      g.follow('#game-goal', () => ({x: 55, y: 170, w: 429, h: 57}));
      g.follow('#game-player', () => {
        const camera = g.data.album?.camera;
        return camera && {x: camera.x - 60, y: camera.y - 60, w: 120, h: 120};
      });
      g.follow('#game-target', () => album);
    },
    reset(g, index) {
      g.pointer.down = false;
      g.data.album = {
        level: levels[index], time: 0, camera: {x: 479, y: 566}, focus: 0,
        shots: [], flash: 0, held: false, used: false, offFocus: 0, hinted: false
      };
    },
    autopilot(g) {
      const d = g.data.album;
      const subject = resolveSpecies(d.level);
      const pt = target(d.shots.length, swim(d.level, d.time), subject);
      Object.assign(g.pointer, {x: pt.x, y: pt.y, down: true, active: true});
    },
    update(g, dt) {
      const d = g.data.album;
      d.time += dt;
      d.flash = Math.max(0, d.flash - dt);
      const p = g.pointer;
      const keys = g.keys;
      const keyboard = keys.left || keys.right || keys.up || keys.down || keys.jump;
      const holding = keys.jump || (p.down && p.x >= scene.x && p.x <= scene.x + scene.w &&
        p.y >= scene.y && p.y <= scene.y + scene.h);
      d.held = Boolean(holding);
      if (holding) d.used = true;
      const camera = d.camera;
      const x = keyboard ? camera.x + (Number(Boolean(keys.right)) - Number(Boolean(keys.left))) * 500 * dt : p.x;
      const y = keyboard ? camera.y + (Number(Boolean(keys.down)) - Number(Boolean(keys.up))) * 500 * dt : p.y;
      if (holding || keyboard) {
        const dx = limit(x, 96, 818) - camera.x;
        const dy = limit(y, 229, 610) - camera.y;
        const ratio = Math.min(1, (975 * dt) / Math.max(1, Math.hypot(dx, dy)));
        camera.x += dx * ratio;
        camera.y += dy * ratio;
      }
      if (!holding) {
        d.focus = 0; d.offFocus = 0; d.hinted = false;
        return;
      }
      const subject = resolveSpecies(d.level);
      if (!ready(subject.image)) return;
      const fish = swim(d.level, d.time);
      if (fish.turning) {
        d.focus = 0;
        return;
      }
      const pt = target(d.shots.length, fish, subject);
      const distance = Math.hypot(camera.x - pt.x, camera.y - pt.y);
      if (distance > d.level.r) {
        d.focus = Math.max(0, d.focus - dt * 2);
        d.offFocus += dt;
        if (d.offFocus >= 1.05 && !d.hinted) {
          d.hinted = true;
          g.say('看看观察册里亮着的那一格。', 'no', 2.0);
        }
        return;
      }
      d.offFocus = 0;
      d.focus += dt;
      if (d.focus < exposure) return;
      d.shots.push({part: d.shots.length, subject, fish});
      d.focus = 0; d.hinted = false; d.flash = .18;
      K.sfx.pick();
      g.sparkle(camera.x, camera.y, '#ffe7a1');
      if (d.shots.length === 3) g.win();
      else g.say('拍到了！把相机拖向下一处。', 'ok', .95);
    },
    idle(g, dt) {
      const d = g.data.album;
      if (d) d.flash = Math.max(0, d.flash - dt);
    },
    draw
  });
})();

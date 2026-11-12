const supplies = {
  foot2: "__IMG:load-football-2__",
  foot3: "__IMG:load-football-3__",
  basket1: "__IMG:load-basketball-1__",
  basket2: "__IMG:load-basketball-2__",
  basket3: "__IMG:load-basketball-3__",
  ping2: "__IMG:load-ping-pong-2__",
  ping3: "__IMG:load-ping-pong-3__",
  ping4: "__IMG:load-ping-pong-4__"
};
const places = {
  tabletop: "__IMG:at-top__",
  deskBelow: "__IMG:at-bottom__",
  boxInside: "__IMG:inside-box__",
  chairBelow: "__IMG:below-chair__"
};
const icons = {...supplies, ...places};
const cards = Object.fromEntries(Object.entries(icons).map(([id, src]) => {
  const image = new Image();
  image.src = src;
  return [id, image];
}));
const hints = ["再听球和位置。", "看发亮的位置，再按方键。"];
const cuesFor = (steps) => ({
  goal: steps[0], steps, hint: "deliver-hint", hint2: "deliver-help", praise: "deliver-praise"
});

K.ready({title: "送到图上指定的地方", sub: "用箭头开车。方键拿球；再听地点，开到位置图标交付。"});

const options = K.gameTemplates.listenDelivery({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cuesFor(["load-foot-two", "drop-below", "load-basket-one", "drop-top"]),
    cuesFor(["load-ping-three", "drop-box", "load-basket-two", "drop-chair"]),
    cuesFor(["load-basket-two", "drop-chair", "load-foot-three", "drop-below", "load-ping-four", "drop-top-many"])
  ],
  art: {
    backdrop: "__IMG:equipment-corner__", sticker: "__IMG:star__",
    frames: ["__IMG:cart__", "__IMG:cart__"], icons
  },
  doneText: "球都送到了指定位置！",
  levels: [
    {
      pickup: [["foot2",4],["foot3",2],["basket1",6]],
      drop: [["deskBelow",4],["tabletop",2]], orders: [["foot2","deskBelow"],["basket1","tabletop"]],
      lanes: [{row:2,speed:.72,spacing:5.7,phase:1.3}], step:.35, hints
    },
    {
      pickup: [["ping3",2],["ping2",4],["basket2",6],["basket3",8]],
      drop: [["tabletop",1],["boxInside",4],["chairBelow",7]],
      orders: [["ping3","boxInside"],["basket2","chairBelow"]],
      lanes: [{row:1,speed:.88,spacing:5.1,phase:1.6},{row:3,speed:-1.14,spacing:4.9,phase:2.2}], step:.30, hints
    },
    {
      pickup: [["basket2",2],["foot3",4],["ping4",6],["ping3",8]],
      drop: [["chairBelow",1],["deskBelow",4],["tabletop",7]],
      orders: [["basket2","chairBelow"],["foot3","deskBelow"],["ping4","tabletop"]],
      lanes: [{row:1,speed:1.2,spacing:4.9,phase:2.2},{row:2,speed:-1.35,spacing:4.6,phase:.4},{row:3,speed:1.47,spacing:4.9,phase:1.5}], step:.26, hints
    }
  ]
});

function panel(context, x, y, w, h, r, colour) {
  context.fillStyle = colour;
  K.draw.rr(context, x, y, w, h, r);
  context.fill();
}

const supplyTop = (index) => 97 + index * 119;
const draw = options.draw;
options.draw = (frame, context) => {
  draw(frame, context);
  const {w: world, level} = frame.data;
  if (!world) return;
  const order = level.orders[world.order];
  level.pickup.forEach(([id], index) => {
    const top = supplyTop(index);
    const isHint = world.help && world.carried === null && id === order?.[0];
    panel(context, 20, top, 204, 105, 15, isHint ? "#ffcc69" : "#537368");
    panel(context, 26, top + 6, 192, 93, 10, "#fff0d6");
    if (cards[id].naturalWidth) context.drawImage(cards[id], 68, top + 7, 106, 92);
  });
  level.drop.forEach(([id], index) => {
    const x = 1058 + (index % 2) * 98;
    const y = 352 + Math.floor(index / 2) * 99;
    const isHint = world.help && world.carried !== null && id === order?.[1];
    panel(context, x, y, 92, 93, 12, isHint ? "#ffcc69" : "#537368");
    if (cards[id].naturalWidth) context.drawImage(cards[id], x + 4, y + 6, 84, 74);
  });
};
options.onState = (_frame, state) => {
  if (state.demo === false) K.$$(".teach-hl").forEach((anchor) => anchor.classList.remove("teach-hl"));
};

const game = K.game(options);
game.follow("#first-gear-card", () => ({x: 20, y: supplyTop(0), w: 204, h: 105}));
game.follow("#first-pickup-spot", () => ({x: 602, y: 497, w: 76, h: 78}));
game.follow("#delivery-replay-anchor", () => {
  const button = K.$(".arc-voice");
  return button && button.offsetWidth ? K.pos(button) : null;
});

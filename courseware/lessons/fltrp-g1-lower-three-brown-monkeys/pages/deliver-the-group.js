const icons = {
  white2: "__IMG:two-white-horses__", white3: "__IMG:three-white-horses__", brown2: "__IMG:two-brown-horses__",
  monkey4: "__IMG:four-monkeys__", monkey3: "__IMG:three-monkeys__", yellow4: "__IMG:four-yellow-birds__",
  brown4: "__IMG:four-brown-horses__", green5: "__IMG:five-green-birds__", green6: "__IMG:six-green-birds__",
  yellow5: "__IMG:five-yellow-birds__", snake5: "__IMG:five-green-snakes__",
  sun: "__IMG:marker-sun__", leaf: "__IMG:marker-leaf__", cloud: "__IMG:marker-cloud__"
};
const goods = {
  white2: [2, "#f8e7c5", "horse"], white3: [3, "#f8e7c5", "horse"], brown2: [2, "#a75b3b", "horse"],
  monkey4: [4, "#a75b3b", "monkey"], monkey3: [3, "#a75b3b", "monkey"], yellow4: [4, "#e4b93e", "bird"],
  brown4: [4, "#a75b3b", "horse"], green5: [5, "#669b4c", "bird"], green6: [6, "#669b4c", "bird"],
  yellow5: [5, "#e4b93e", "bird"], snake5: [5, "#669b4c", "snake"]
};
const pictures = Object.fromEntries(Object.keys(goods).map((id) => {
  const image = new Image();
  image.src = icons[id];
  return [id, image];
}));
const hints = ["再听，再核对三条线索。", "图卡亮了，开到它那儿。"];
const makeCues = (steps) => ({goal: steps[0], steps, hint: "delivery-hint", hint2: "delivery-help", praise: "delivery-praise"});

K.ready({title: "听完整口令再送图", sub: "先找相符的图卡，再用方向箭头开车。停稳后点方键拿取或交付。"});

const options = K.gameTemplates.listenDelivery({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    makeCues(["pick-white-two", "to-sun", "pick-white-three", "to-leaf"]),
    makeCues(["pick-monkey-four", "to-leaf", "pick-yellow-four", "to-cloud", "pick-brown-four", "to-sun"]),
    makeCues(["pick-green-five", "to-cloud", "pick-green-six", "to-sun", "pick-yellow-five", "to-leaf"])
  ],
  art: {
    backdrop: "__IMG:delivery-court__", sticker: "__IMG:monkey-badge__",
    frames: ["__IMG:zoo-rover__", "__IMG:zoo-rover__", "__IMG:obstacle-rover__"], icons
  },
  doneText: "三条线索都找对，动物图卡送到了！",
  levels: [
    {pickup: [["white2",4],["brown2",2],["white3",6]],
      drop: [["sun",4],["leaf",2]], orders: [["white2","sun"],["white3","leaf"]],
      lanes: [{row:2,speed:.72,spacing:5.7,phase:1.3}], step:.35, hints},
    {pickup: [["monkey4",2],["yellow4",4],["monkey3",6],["brown4",8]],
      drop: [["sun",1],["leaf",4],["cloud",7]], orders: [["monkey4","leaf"],["yellow4","cloud"],["brown4","sun"]],
      lanes: [{row:1,speed:.88,spacing:5.1,phase:1.6},{row:3,speed:-1.14,spacing:4.9,phase:2.2}], step:.30, hints},
    {pickup: [["green5",2],["yellow5",4],["green6",6],["snake5",8]],
      drop: [["cloud",1],["sun",4],["leaf",7]], orders: [["green5","cloud"],["green6","sun"],["yellow5","leaf"]],
      lanes: [{row:1,speed:1.2,spacing:4.9,phase:2.2},{row:2,speed:-1.35,spacing:4.6,phase:.4},{row:3,speed:1.47,spacing:4.9,phase:1.5}], step:.26, hints}
  ]
});

const paint = (context, x, y, width, height, radius, fill) => {
  context.fillStyle = fill;
  K.draw.rr(context, x, y, width, height, radius);
  context.fill();
};
const cardTop = (i) => 94 + i * 122;

function fallbackCard(context, id, left, top) {
  const [n,color,animal] = goods[id];
  const rows = n > 3 ? 2 : 1;
  const cols = Math.ceil(n / rows);
  for (let i = 0; i < n; i += 1) {
    const x = left + 106 + (i % cols - (cols - 1) / 2) * 45;
    const y = top + 54 + (Math.floor(i / cols) - (rows - 1) / 2) * 38;
    context.fillStyle = color;
    if (animal === "snake") {
      context.strokeStyle = color;
      context.lineWidth = 7;
      context.beginPath();
      context.moveTo(x - 14,y + 7);
      context.bezierCurveTo(x - 7,y - 17,x + 1,y + 17,x + 14,y - 6);
      context.stroke();
    } else {
      K.draw.circle(context,x,y,11);
      if (animal === "monkey") {
        K.draw.circle(context,x - 10,y - 7,5);
        K.draw.circle(context,x + 10,y - 7,5);
      }
      if (animal === "horse") paint(context,x + 4,y - 13,12,14,3,color);
      if (animal === "bird") paint(context,x + 7,y - 5,10,5,2,"#8b5c3b");
    }
  }
}

const draw = options.draw;
options.draw = (frame, context) => {
  draw(frame,context);
  const {w: world, level} = frame.data;
  if (!world) return;
  level.pickup.forEach(([id], i) => {
    const y = cardTop(i);
    const selected = world.help && world.carried === null && id === level.orders[world.order]?.[0];
    paint(context, 19, y, 212, 110, 17, selected ? "#ffd474" : "#517761");
    paint(context, 25, y + 6, 200, 98, 12, "#f7edcf");
    const pic = pictures[id];
    if (pic.naturalWidth) context.drawImage(pic, 30, y + 9, 190, 92);
    else fallbackCard(context,id,19,y);
  });
};
options.onState = (_frame, state) => {
  if (state.demo === false) K.$$(".teach-hl").forEach((anchor) => anchor.classList.remove("teach-hl"));
};

const game = K.game(options);
game.follow("#first-listening-card", () => ({x: 19, y: cardTop(0), w: 212, h: 110}));
game.follow("#first-loading-bay", () => ({x: 602, y: 497, w: 76, h: 78}));
game.follow("#delivery-replay-anchor", () => {
  const button = K.$(".arc-voice");
  return button && button.offsetWidth ? K.pos(button) : null;
});

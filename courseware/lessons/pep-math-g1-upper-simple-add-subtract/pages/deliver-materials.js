const deliveryCues = (steps) => ({
  goal: steps[0], steps, hint: "delivery-hint", hint2: "delivery-help", praise: "delivery-praise"
});

K.ready({
  title: "风筝节送货车",
  sub: "听单拿货，算清添减后的数量，等车过去再交货。"
});

const courier = K.game(K.gameTemplates.listenDelivery({
  voiceLead: true,
  stepVoiceLead: true,
  cues: [
    deliveryCues(["stock-twelve", "plus-five"]),
    deliveryCues(["stock-thirteen", "plus-three", "stock-eighteen", "minus-four"]),
    deliveryCues(["stock-eleven", "plus-six", "stock-nineteen", "minus-five",
                  "stock-sixteen", "minus-four"])
  ],
  art: {
    backdrop: "__IMG:courier-yard__", sticker: "__IMG:festival-sticker__",
    frames: ["__IMG:courier-ready__", "__IMG:courier-load__", "__IMG:traffic-cart__"],
    icons: {
      "stock-11": "__IMG:stock-11__", "stock-12": "__IMG:stock-12__",
      "stock-13": "__IMG:stock-13__", "stock-14": "__IMG:stock-14__",
      "stock-16": "__IMG:stock-16__", "stock-18": "__IMG:stock-18__",
      "stock-19": "__IMG:stock-19__", "dock-12": "__IMG:dock-12__",
      "dock-14": "__IMG:dock-14__", "dock-16": "__IMG:dock-16__",
      "dock-17": "__IMG:dock-17__", "dock-18": "__IMG:dock-18__"
    }
  },
  doneText: "算准了每张材料单，所有货都送到了！",
  levels: [
    {
      pickup: [["stock-12", 4], ["stock-14", 6]],
      drop: [["dock-17", 4], ["dock-12", 6]],
      orders: [["stock-12", "dock-17"]],
      lanes: [{row: 2, speed: 0.86, spacing: 5.7, phase: 1.4}],
      step: 0.34,
      hints: ["重听这一步。是要取原数，还是送算出的数？", "整盒十不变，再数添去以后有几个一。"]
    },
    {
      pickup: [["stock-13", 2], ["stock-18", 6], ["stock-16", 8]],
      drop: [["dock-16", 1], ["dock-14", 5], ["dock-18", 8]],
      orders: [["stock-13", "dock-16"], ["stock-18", "dock-14"]],
      lanes: [{row: 1, speed: -1.22, spacing: 4.7, phase: 2.1},
              {row: 3, speed: 1.30, spacing: 4.9, phase: 1.1}],
      step: 0.26,
      hints: ["听清是再添几枚，还是拿走几枚。", "小车可以在空地等一等，看看发亮的地方。"]
    },
    {
      pickup: [["stock-11", 1], ["stock-19", 4], ["stock-16", 7]],
      drop: [["dock-14", 6], ["dock-17", 2], ["dock-12", 4], ["dock-16", 8]],
      orders: [["stock-11", "dock-17"], ["stock-19", "dock-14"], ["stock-16", "dock-12"]],
      lanes: [{row: 1, speed: -1.77, spacing: 4.2, phase: 0.9},
              {row: 2, speed: 1.57, spacing: 4.3, phase: 2.2},
              {row: 3, speed: -1.58, spacing: 4.2, phase: 1.5}],
      step: 0.21,
      hints: ["底下是取货图，上面是结果图，别把原数送过去。", "先等车道有空，再去计数器图标的站点。"]
    }
  ]
}));

courier.follow("#delivery-first-stock", () => ({x: 602, y: 497, w: 76, h: 78}));
courier.follow("#delivery-road", () => ({x: 254, y: 322, w: 772, h: 84}));
courier.follow("#delivery-receiving", () => ({x: 568, y: 151, w: 296, h: 78}));

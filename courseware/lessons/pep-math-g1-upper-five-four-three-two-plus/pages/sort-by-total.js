K.ready({"title": "按总数送到站", "sub": "从货牌背后推，送到总数一样的站。"});

K.game(K.gameTemplates.sortingDepot({
  "art": {
    "backdrop": "__IMG:workshop-stage__",
    "sticker": "__IMG:kite-sticker__",
    "icons": {
      "station-11": "__IMG:station-11__",
      "station-12": "__IMG:station-12__",
      "station-13": "__IMG:station-13__",
      "station-14": "__IMG:station-14__",
      "t3-8": "__IMG:t3-8__",
      "t3-9": "__IMG:t3-9__",
      "t4-8": "__IMG:t4-8__",
      "t4-9": "__IMG:t4-9__",
      "t5-9": "__IMG:t5-9__",
      "t9-3": "__IMG:t9-3__"
    },
    "frames": [
      "__IMG:kite-cart__",
      "__IMG:kite-cart-moving__"
    ]
  },
  "voiceLead": true,
  "doneText": "纸鸢材料准备好啦！",
  "cues": [
    {
      "goal": "sort-by-total-goal",
      "hint": "sort-by-total-hint",
      "hint2": "sort-by-total-hint2",
      "praise": "sort-by-total-praise"
    },
    {
      "goal": "sort-by-total-goal",
      "hint": "sort-by-total-hint",
      "hint2": "sort-by-total-hint2",
      "praise": "sort-by-total-praise"
    },
    {
      "goal": "sort-by-total-goal",
      "hint": "sort-by-total-hint",
      "hint2": "sort-by-total-hint2",
      "praise": "sort-by-total-praise"
    }
  ],
  "levels": [
    {
      "map": [
        "########",
        "#......#",
        "#.S....#",
        "#......#",
        "########"
      ],
      "step": 0.32,
      "items": [
        {
          "x": 3,
          "y": 2,
          "token": "t3-8",
          "group": 11
        },
        {
          "x": 3,
          "y": 3,
          "token": "t3-9",
          "group": 12
        }
      ],
      "docks": [
        {
          "x": 5,
          "y": 2,
          "sample": "station-11",
          "group": 11
        },
        {
          "x": 5,
          "y": 3,
          "sample": "station-12",
          "group": 12
        }
      ],
      "hints": [
        "先数货牌的两堆，再比站上的总数。",
        "从货牌背后推。碰到堵路，可以撤回一步。"
      ]
    },
    {
      "map": [
        "#########",
        "#.......#",
        "#..#....#",
        "#.S.....#",
        "#.......#",
        "#########"
      ],
      "step": 0.26,
      "items": [
        {
          "x": 4,
          "y": 2,
          "token": "t3-9",
          "group": 12
        },
        {
          "x": 4,
          "y": 4,
          "token": "t9-3",
          "group": 12
        },
        {
          "x": 3,
          "y": 3,
          "token": "t4-9",
          "group": 13
        }
      ],
      "docks": [
        {
          "x": 6,
          "y": 2,
          "sample": "station-12",
          "group": 12
        },
        {
          "x": 7,
          "y": 4,
          "sample": "station-12",
          "group": 12
        },
        {
          "x": 6,
          "y": 3,
          "sample": "station-13",
          "group": 13
        }
      ],
      "hints": [
        "先数货牌的两堆，再比站上的总数。",
        "从货牌背后推。碰到堵路，可以撤回一步。"
      ]
    },
    {
      "map": [
        "##########",
        "#........#",
        "#..#.....#",
        "#.S......#",
        "#....#...#",
        "#........#",
        "##########"
      ],
      "step": 0.22,
      "items": [
        {
          "x": 4,
          "y": 3,
          "token": "t3-9",
          "group": 12
        },
        {
          "x": 7,
          "y": 4,
          "token": "t4-8",
          "group": 12
        },
        {
          "x": 4,
          "y": 2,
          "token": "t4-9",
          "group": 13
        },
        {
          "x": 4,
          "y": 5,
          "token": "t5-9",
          "group": 14
        }
      ],
      "docks": [
        {
          "x": 7,
          "y": 3,
          "sample": "station-12",
          "group": 12
        },
        {
          "x": 8,
          "y": 4,
          "sample": "station-12",
          "group": 12
        },
        {
          "x": 8,
          "y": 2,
          "sample": "station-13",
          "group": 13
        },
        {
          "x": 7,
          "y": 5,
          "sample": "station-14",
          "group": 14
        }
      ],
      "hints": [
        "先数货牌的两堆，再比站上的总数。",
        "从货牌背后推。碰到堵路，可以撤回一步。"
      ]
    }
  ]
}));

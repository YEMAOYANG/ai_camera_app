K.ready({"title": "字卡搬到哪个托盘", "sub": "找相同的部件，再把字卡推过去。"});

K.game(K.gameTemplates.sortingDepot({
  "voiceLead": true,
  "art": {
    "backdrop": "__IMG:depot-backdrop__",
    "frames": [
      "__IMG:depot-cart__",
      "__IMG:depot-cart-push__"
    ],
    "icons": {
      "song": "__IMG:radical-song__",
      "miao": "__IMG:radical-miao__",
      "zhi": "__IMG:radical-zhi__",
      "fen": "__IMG:radical-fen__",
      "jing": "__IMG:radical-jing__",
      "bai": "__IMG:radical-bai__",
      "feng": "__IMG:radical-feng__",
      "yin": "__IMG:radical-yin__",
      "mo": "__IMG:radical-mo__",
      "dock-mu": "__IMG:dock-mu__",
      "dock-cao": "__IMG:dock-cao__"
    },
    "sticker": "__IMG:garden-reward__"
  },
  "doneText": "每张字卡都回到了同组托盘！",
  "cues": [
    {
      "goal": "two-cards",
      "hint": "radical-hint",
      "hint2": "radical-help",
      "praise": "radical-praise"
    },
    {
      "goal": "three-cards",
      "hint": "radical-hint",
      "hint2": "radical-help",
      "praise": "radical-praise"
    },
    {
      "goal": "four-cards",
      "hint": "radical-hint",
      "hint2": "radical-help",
      "praise": "radical-praise"
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
      "step": 0.3,
      "items": [
        {
          "x": 3,
          "y": 2,
          "token": "song",
          "group": "mu"
        },
        {
          "x": 3,
          "y": 3,
          "token": "miao",
          "group": "cao"
        }
      ],
      "docks": [
        {
          "x": 5,
          "y": 2,
          "sample": "dock-mu",
          "group": "mu"
        },
        {
          "x": 5,
          "y": 3,
          "sample": "dock-cao",
          "group": "cao"
        }
      ],
      "hints": [
        "看看字的左边和上边，找相同的部件。",
        "车只能推。绕到卡片另一侧，或按回转键。"
      ],
      "labels": {
        "song": "松",
        "miao": "苗",
        "dock-mu": "木",
        "dock-cao": "艹"
      }
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
      "step": 0.23,
      "items": [
        {
          "x": 4,
          "y": 2,
          "token": "zhi",
          "group": "mu"
        },
        {
          "x": 4,
          "y": 4,
          "token": "fen",
          "group": "cao"
        },
        {
          "x": 3,
          "y": 3,
          "token": "jing",
          "group": "cao"
        }
      ],
      "docks": [
        {
          "x": 6,
          "y": 2,
          "sample": "dock-mu",
          "group": "mu"
        },
        {
          "x": 7,
          "y": 4,
          "sample": "dock-cao",
          "group": "cao"
        },
        {
          "x": 6,
          "y": 3,
          "sample": "dock-cao",
          "group": "cao"
        }
      ],
      "hints": [
        "看看字的左边和上边，找相同的部件。",
        "车只能推。绕到卡片另一侧，或按回转键。"
      ],
      "labels": {
        "zhi": "枝",
        "fen": "芬",
        "jing": "茎",
        "dock-mu": "木",
        "dock-cao": "艹"
      }
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
      "step": 0.19,
      "items": [
        {
          "x": 4,
          "y": 3,
          "token": "bai",
          "group": "mu"
        },
        {
          "x": 7,
          "y": 4,
          "token": "feng",
          "group": "mu"
        },
        {
          "x": 4,
          "y": 2,
          "token": "yin",
          "group": "cao"
        },
        {
          "x": 4,
          "y": 5,
          "token": "mo",
          "group": "cao"
        }
      ],
      "docks": [
        {
          "x": 7,
          "y": 3,
          "sample": "dock-mu",
          "group": "mu"
        },
        {
          "x": 8,
          "y": 4,
          "sample": "dock-mu",
          "group": "mu"
        },
        {
          "x": 8,
          "y": 2,
          "sample": "dock-cao",
          "group": "cao"
        },
        {
          "x": 7,
          "y": 5,
          "sample": "dock-cao",
          "group": "cao"
        }
      ],
      "hints": [
        "看看字的左边和上边，找相同的部件。",
        "车只能推。绕到卡片另一侧，或按回转键。"
      ],
      "labels": {
        "bai": "柏",
        "feng": "枫",
        "yin": "荫",
        "mo": "茉",
        "dock-mu": "木",
        "dock-cao": "艹"
      }
    }
  ]
}));

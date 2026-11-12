K.ready({"title": "推报名卡，送到同一运动区", "sub": "按卡上的喜好，把队员送到对应场地。"});

K.game(K.gameTemplates.sortingDepot({
  "art": {
    "backdrop": "__IMG:sport-stage__",
    "sticker": "__IMG:sport-sticker__",
    "frames": [
      "__IMG:sport-cart__",
      "__IMG:sport-cart-action__"
    ],
    "icons": {
      "foot-a": "__IMG:sport-depot-foot-a__",
      "foot-b": "__IMG:sport-depot-foot-b__",
      "basket-a": "__IMG:sport-depot-basket-a__",
      "basket-b": "__IMG:sport-depot-basket-b__",
      "ping": "__IMG:sport-depot-ping__",
      "goal": "__IMG:sport-goal__",
      "hoop": "__IMG:sport-hoop__",
      "table": "__IMG:sport-ping-table__"
    }
  },
  "voiceLead": true,
  "doneText": "各队都报名了！",
  "cues": [
    {
      "goal": "d-first",
      "hint": "d-hint",
      "hint2": "d-help",
      "praise": "d-good"
    },
    {
      "goal": "d-second",
      "hint": "d-hint",
      "hint2": "d-help",
      "praise": "d-good"
    },
    {
      "goal": "d-third",
      "hint": "d-hint",
      "hint2": "d-help",
      "praise": "d-good"
    }
  ],
  "levels": [
    {
      "map": [
        "#########",
        "#.......#",
        "#.S.....#",
        "#.......#",
        "#########"
      ],
      "step": 0.3,
      "items": [
        {
          "x": 3,
          "y": 2,
          "token": "foot-a",
          "group": "football"
        },
        {
          "x": 6,
          "y": 2,
          "token": "basket-a",
          "group": "basketball"
        }
      ],
      "docks": [
        {
          "x": 5,
          "y": 2,
          "sample": "goal",
          "group": "football"
        },
        {
          "x": 5,
          "y": 3,
          "sample": "hoop",
          "group": "basketball"
        }
      ],
      "hints": [
        "认出卡上的运动，再看场地器材。",
        "绕到卡后面。想换路线，可以撤回。"
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
      "step": 0.25,
      "items": [
        {
          "x": 4,
          "y": 2,
          "token": "foot-b",
          "group": "football"
        },
        {
          "x": 4,
          "y": 4,
          "token": "ping",
          "group": "ping"
        },
        {
          "x": 3,
          "y": 3,
          "token": "basket-b",
          "group": "basketball"
        }
      ],
      "docks": [
        {
          "x": 6,
          "y": 2,
          "sample": "goal",
          "group": "football"
        },
        {
          "x": 7,
          "y": 4,
          "sample": "table",
          "group": "ping"
        },
        {
          "x": 6,
          "y": 3,
          "sample": "hoop",
          "group": "basketball"
        }
      ],
      "hints": [
        "认出卡上的运动，再看场地器材。",
        "绕到卡后面。想换路线，可以撤回。"
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
      "step": 0.2,
      "items": [
        {
          "x": 4,
          "y": 3,
          "token": "foot-a",
          "group": "football"
        },
        {
          "x": 7,
          "y": 4,
          "token": "basket-b",
          "group": "basketball"
        },
        {
          "x": 4,
          "y": 2,
          "token": "basket-a",
          "group": "basketball"
        },
        {
          "x": 4,
          "y": 5,
          "token": "ping",
          "group": "ping"
        }
      ],
      "docks": [
        {
          "x": 7,
          "y": 3,
          "sample": "goal",
          "group": "football"
        },
        {
          "x": 8,
          "y": 4,
          "sample": "hoop",
          "group": "basketball"
        },
        {
          "x": 8,
          "y": 2,
          "sample": "hoop",
          "group": "basketball"
        },
        {
          "x": 7,
          "y": 5,
          "sample": "table",
          "group": "ping"
        }
      ],
      "hints": [
        "认出卡上的运动，再看场地器材。",
        "绕到卡后面。想换路线，可以撤回。"
      ]
    }
  ]
}));

K.ready({"title": "弹珠找同和", "sub": "听目标和，调炮口，打中同一总数的图卡。"});

K.game(K.gameTemplates.magnetMarbles({
  "art": {
    "backdrop": "__IMG:lantern-stage__",
    "sticker": "__IMG:lantern-sticker__",
    "frames": [
      "__IMG:lantern-marble__"
    ],
    "icons": {
      "card-6-5": "__IMG:card-6-5__",
      "card-6-6": "__IMG:card-6-6__",
      "card-6-7": "__IMG:card-6-7__",
      "card-6-8": "__IMG:card-6-8__",
      "card-7-5": "__IMG:card-7-5__",
      "card-8-5": "__IMG:card-8-5__",
      "card-8-6": "__IMG:card-8-6__",
      "card-8-8": "__IMG:card-8-8__",
      "card-9-4": "__IMG:card-9-4__",
      "card-9-5": "__IMG:card-9-5__",
      "card-9-7": "__IMG:card-9-7__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "doneText": "等和卡片找齐啦！",
  "cues": [
    {
      "goal": "sum-twelve",
      "hint": "sum-hint",
      "hint2": "sum-help",
      "praise": "sum-good",
      "steps": [
        "sum-twelve",
        "sum-twelve"
      ]
    },
    {
      "goal": "sum-thirteen",
      "hint": "sum-hint",
      "hint2": "sum-help",
      "praise": "sum-good",
      "steps": [
        "sum-thirteen",
        "sum-thirteen",
        "sum-thirteen"
      ]
    },
    {
      "goal": "sum-fourteen",
      "hint": "sum-hint",
      "hint2": "sum-help",
      "praise": "sum-good",
      "steps": [
        "sum-fourteen",
        "sum-sixteen",
        "sum-fourteen",
        "sum-sixteen"
      ]
    }
  ],
  "levels": [
    {
      "queue": [
        12,
        12
      ],
      "targets": [
        {
          "x": 470,
          "value": "card-6-6"
        },
        {
          "x": 640,
          "value": "card-6-5"
        },
        {
          "x": 811,
          "value": "card-7-5"
        }
      ],
      "pairs": [
        [
          12,
          "card-6-6"
        ],
        [
          11,
          "card-6-5"
        ],
        [
          12,
          "card-7-5"
        ]
      ],
      "targetWidth": 165,
      "targetHeight": 114,
      "speed": 440,
      "drift": 5,
      "listenOnly": true,
      "hints": [
        "先把牌上的两组数合起来，再瞄准。",
        "算一算和。发亮的牌可以先看。"
      ]
    },
    {
      "queue": [
        13,
        13,
        13
      ],
      "targets": [
        {
          "x": 341,
          "value": "card-9-4"
        },
        {
          "x": 535,
          "value": "card-8-6"
        },
        {
          "x": 728,
          "value": "card-8-5"
        },
        {
          "x": 915,
          "value": "card-6-7"
        }
      ],
      "pairs": [
        [
          13,
          "card-9-4"
        ],
        [
          14,
          "card-8-6"
        ],
        [
          13,
          "card-8-5"
        ],
        [
          13,
          "card-6-7"
        ]
      ],
      "targetWidth": 156,
      "targetHeight": 114,
      "speed": 485,
      "drift": 8,
      "listenOnly": true,
      "hints": [
        "先把牌上的两组数合起来，再瞄准。",
        "算一算和。发亮的牌可以先看。"
      ]
    },
    {
      "queue": [
        14,
        16,
        14,
        16
      ],
      "targets": [
        {
          "x": 330,
          "value": "card-9-5"
        },
        {
          "x": 485,
          "value": "card-8-8"
        },
        {
          "x": 640,
          "value": "card-8-5"
        },
        {
          "x": 795,
          "value": "card-6-8"
        },
        {
          "x": 951,
          "value": "card-9-7"
        }
      ],
      "pairs": [
        [
          14,
          "card-9-5"
        ],
        [
          16,
          "card-8-8"
        ],
        [
          13,
          "card-8-5"
        ],
        [
          14,
          "card-6-8"
        ],
        [
          16,
          "card-9-7"
        ]
      ],
      "targetWidth": 133,
      "targetHeight": 114,
      "speed": 530,
      "drift": 12,
      "listenOnly": true,
      "hints": [
        "先把牌上的两组数合起来，再瞄准。",
        "算一算和。发亮的牌可以先看。"
      ]
    }
  ]
}));

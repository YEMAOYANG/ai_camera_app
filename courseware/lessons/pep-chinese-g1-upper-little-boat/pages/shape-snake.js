K.ready({"title": "弯和尖都对，小蛇才长长", "sub": "沿弯弯的边看过去，两个端头都要尖。"});

K.game(K.gameTemplates.compareSnake({
  "voiceLead": true,
  "art": {
    "backdrop": "__IMG:snake-backdrop__",
    "frames": [
      "__IMG:snake-head__",
      "__IMG:snake-body__",
      "__IMG:snake-tail__"
    ],
    "icons": {
      "shape-moon": "__IMG:shape-moon__",
      "shape-boat": "__IMG:shape-boat__",
      "moon-tilted": "__IMG:shape-crescent-side__",
      "shape-boat-side": "__IMG:shape-boat-side__",
      "shape-disc": "__IMG:shape-disc__",
      "shape-rounded": "__IMG:shape-rounded__",
      "shape-straight": "__IMG:shape-straight__"
    },
    "sticker": "__IMG:boat-reward__"
  },
  "doneText": "你抓住了弯边和两个尖端！",
  "cues": [
    {
      "goal": "shape-goal",
      "hint": "shape-hint",
      "hint2": "shape-help",
      "praise": "shape-praise"
    },
    {
      "goal": "shape-goal",
      "hint": "shape-hint",
      "hint2": "shape-help",
      "praise": "shape-praise"
    },
    {
      "goal": "shape-goal",
      "hint": "shape-hint",
      "hint2": "shape-help",
      "praise": "shape-praise"
    }
  ],
  "levels": [
    {
      "start": "shape-moon",
      "seconds": 0.82,
      "walls": [],
      "groups": {
        "shape-moon": "curved-two-points",
        "shape-boat": "curved-two-points",
        "moon-tilted": "curved-two-points",
        "shape-boat-side": "curved-two-points"
      },
      "rounds": [
        {
          "relation": "match",
          "foods": [
            [
              6,
              3,
              "shape-boat"
            ],
            [
              7,
              4,
              "shape-disc"
            ]
          ]
        }
      ],
      "hints": [
        "先沿边比一比，再回头找它的两个端头。",
        "边线要弯，两个端头都要尖。再看哪张两个条件都够。"
      ],
      "labels": {
        "shape-moon": "弯月",
        "shape-boat": "尖头小船",
        "moon-tilted": "转过的弯月",
        "shape-boat-side": "转过的尖船",
        "shape-disc": "圆盘",
        "shape-rounded": "圆头弯片",
        "shape-straight": "直纸梭"
      }
    },
    {
      "start": "shape-moon",
      "seconds": 0.67,
      "walls": [
        [
          4,
          2
        ]
      ],
      "groups": {
        "shape-moon": "curved-two-points",
        "shape-boat": "curved-two-points",
        "moon-tilted": "curved-two-points",
        "shape-boat-side": "curved-two-points"
      },
      "rounds": [
        {
          "relation": "match",
          "foods": [
            [
              5,
              3,
              "moon-tilted"
            ],
            [
              7,
              4,
              "shape-rounded"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              3,
              2,
              "shape-boat"
            ],
            [
              7,
              2,
              "shape-disc"
            ],
            [
              6,
              4,
              "shape-rounded"
            ]
          ]
        }
      ],
      "hints": [
        "先沿边比一比，再回头找它的两个端头。",
        "边线要弯，两个端头都要尖。再看哪张两个条件都够。"
      ],
      "labels": {
        "shape-moon": "弯月",
        "shape-boat": "尖头小船",
        "moon-tilted": "转过的弯月",
        "shape-boat-side": "转过的尖船",
        "shape-disc": "圆盘",
        "shape-rounded": "圆头弯片",
        "shape-straight": "直纸梭"
      }
    },
    {
      "start": "shape-moon",
      "seconds": 0.55,
      "walls": [
        [
          4,
          2
        ],
        [
          6,
          3
        ]
      ],
      "groups": {
        "shape-moon": "curved-two-points",
        "shape-boat": "curved-two-points",
        "moon-tilted": "curved-two-points",
        "shape-boat-side": "curved-two-points"
      },
      "rounds": [
        {
          "relation": "match",
          "foods": [
            [
              5,
              3,
              "shape-boat-side"
            ],
            [
              7,
              4,
              "shape-straight"
            ],
            [
              3,
              4,
              "shape-rounded"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              3,
              2,
              "shape-boat"
            ],
            [
              7,
              2,
              "shape-rounded"
            ],
            [
              8,
              4,
              "shape-straight"
            ]
          ]
        },
        {
          "relation": "match",
          "foods": [
            [
              7,
              1,
              "moon-tilted"
            ],
            [
              2,
              4,
              "shape-straight"
            ],
            [
              2,
              2,
              "shape-disc"
            ]
          ]
        }
      ],
      "hints": [
        "先沿边比一比，再回头找它的两个端头。",
        "边线要弯，两个端头都要尖。再看哪张两个条件都够。"
      ],
      "labels": {
        "shape-moon": "弯月",
        "shape-boat": "尖头小船",
        "moon-tilted": "转过的弯月",
        "shape-boat-side": "转过的尖船",
        "shape-disc": "圆盘",
        "shape-rounded": "圆头弯片",
        "shape-straight": "直纸梭"
      }
    }
  ]
}));

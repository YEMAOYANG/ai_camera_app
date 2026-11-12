K.ready({"title": "听两句，帮衣服找主人", "sub": "先听取什么，再听送给谁。"});

K.game(K.gameTemplates.listenDelivery({
  "art": {
    "backdrop": "__IMG:shore-stage__",
    "sticker": "__IMG:shore-sticker__",
    "frames": [
      "__IMG:shore-van__",
      "__IMG:shore-van-run__",
      "__IMG:shore-traffic__"
    ],
    "icons": {
      "under": "__IMG:shore-pick-under__",
      "beside": "__IMG:shore-pick-beside__",
      "navy": "__IMG:shore-navy-pair__",
      "socks": "__IMG:shore-socks__",
      "leo": "__IMG:shore-leo__",
      "nina": "__IMG:shore-nina__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "doneText": "衣物都送回来了！",
  "cues": [
    {
      "goal": "under",
      "steps": [
        "under",
        "her-shorts"
      ],
      "hint": "route-hint",
      "hint2": "route-help",
      "praise": "route-good"
    },
    {
      "goal": "navy",
      "steps": [
        "navy",
        "her-shoes",
        "socks",
        "his-socks"
      ],
      "hint": "route-hint",
      "hint2": "route-help",
      "praise": "route-good"
    },
    {
      "goal": "under",
      "steps": [
        "under",
        "her-shorts",
        "socks",
        "his-socks",
        "navy",
        "her-shoes"
      ],
      "hint": "route-hint",
      "hint2": "route-help",
      "praise": "route-good"
    }
  ],
  "levels": [
    {
      "pickup": [
        [
          "under",
          3
        ],
        [
          "beside",
          4
        ],
        [
          "navy",
          7
        ]
      ],
      "drop": [
        [
          "leo",
          2
        ],
        [
          "nina",
          6
        ]
      ],
      "orders": [
        [
          "under",
          "nina"
        ]
      ],
      "step": 0.33,
      "lanes": [
        {
          "row": 2,
          "speed": 0.87,
          "spacing": 5.8,
          "phase": 0
        }
      ],
      "hints": [
        "先听清衣物。要是说了鸭子，再核对位置。",
        "停一停重听，再看发亮的图。"
      ]
    },
    {
      "pickup": [
        [
          "navy",
          2
        ],
        [
          "socks",
          5
        ],
        [
          "beside",
          7
        ]
      ],
      "drop": [
        [
          "leo",
          2
        ],
        [
          "nina",
          6
        ]
      ],
      "orders": [
        [
          "navy",
          "nina"
        ],
        [
          "socks",
          "leo"
        ]
      ],
      "step": 0.28,
      "lanes": [
        {
          "row": 1,
          "speed": -1.12,
          "spacing": 5,
          "phase": 2
        },
        {
          "row": 3,
          "speed": 1.22,
          "spacing": 4.8,
          "phase": 1
        }
      ],
      "hints": [
        "先听清衣物。要是说了鸭子，再核对位置。",
        "停一停重听，再看发亮的图。"
      ]
    },
    {
      "pickup": [
        [
          "beside",
          1
        ],
        [
          "under",
          3
        ],
        [
          "navy",
          5
        ],
        [
          "socks",
          8
        ]
      ],
      "drop": [
        [
          "leo",
          2
        ],
        [
          "nina",
          6
        ]
      ],
      "orders": [
        [
          "under",
          "nina"
        ],
        [
          "socks",
          "leo"
        ],
        [
          "navy",
          "nina"
        ]
      ],
      "step": 0.23,
      "lanes": [
        {
          "row": 1,
          "speed": 1.2,
          "spacing": 4.8,
          "phase": 0
        },
        {
          "row": 2,
          "speed": -1.42,
          "spacing": 4.7,
          "phase": 1
        },
        {
          "row": 3,
          "speed": 1.51,
          "spacing": 4.8,
          "phase": 4
        }
      ],
      "hints": [
        "先听清衣物。要是说了鸭子，再核对位置。",
        "停一停重听，再看发亮的图。"
      ]
    }
  ]
}));

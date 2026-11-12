K.ready({"title": "滑字片，给部件找搭档", "sub": "同一条路上配对，拼出右边的字。"});

K.game(K.gameTemplates.slideMerge({
  "art": {
    "backdrop": "__IMG:garden8-stage__",
    "sticker": "__IMG:garden8-sticker__",
    "frames": [
      "__IMG:garden8-merge-cart__",
      "__IMG:garden8-merge-cart-hop__"
    ]
  },
  "voiceLead": true,
  "doneText": "收藏格的字都拼好了！",
  "cues": [
    {
      "goal": "merge-first",
      "hint": "merge-hint",
      "hint2": "merge-help",
      "praise": "merge-good"
    },
    {
      "goal": "merge-next",
      "hint": "merge-hint",
      "hint2": "merge-help",
      "praise": "merge-good"
    },
    {
      "goal": "merge-last",
      "hint": "merge-hint",
      "hint2": "merge-help",
      "praise": "merge-good"
    }
  ],
  "levels": [
    {
      "board": [
        [
          null,
          null,
          null,
          null
        ],
        [
          "mouth",
          null,
          "few",
          null
        ],
        [
          null,
          "king",
          null,
          null
        ],
        [
          null,
          null,
          null,
          "see"
        ]
      ],
      "pairs": [
        [
          "mouth",
          "few",
          "quarrel"
        ],
        [
          "king",
          "see",
          "now"
        ]
      ],
      "targets": [
        "quarrel",
        "now"
      ],
      "seconds": 0.36,
      "labels": {
        "mouth": "口",
        "few": "少",
        "quarrel": "吵",
        "king": "王",
        "see": "见",
        "now": "现",
        "nail": "丁",
        "page": "页",
        "top": "顶",
        "moon": "月",
        "half": "半",
        "fat": "胖",
        "ticket": "票",
        "wind": "风",
        "float": "飘",
        "door": "户",
        "square": "方",
        "house": "房",
        "wood": "木",
        "cross": "交",
        "school": "校",
        "father": "父",
        "ba": "巴",
        "dad": "爸"
      },
      "hints": [
        "先找搭档，把两块滑到同一条路。",
        "试一试发亮的方向。也可以按回转键重新摆。"
      ]
    },
    {
      "board": [
        [
          "nail",
          null,
          "moon",
          "page"
        ],
        [
          null,
          null,
          null,
          null
        ],
        [
          "half",
          null,
          "ticket",
          "wind"
        ],
        [
          null,
          null,
          null,
          null
        ]
      ],
      "walls": [
        5
      ],
      "pairs": [
        [
          "nail",
          "page",
          "top"
        ],
        [
          "moon",
          "half",
          "fat"
        ],
        [
          "ticket",
          "wind",
          "float"
        ]
      ],
      "targets": [
        "top",
        "fat",
        "float"
      ],
      "seconds": 0.28,
      "labels": {
        "mouth": "口",
        "few": "少",
        "quarrel": "吵",
        "king": "王",
        "see": "见",
        "now": "现",
        "nail": "丁",
        "page": "页",
        "top": "顶",
        "moon": "月",
        "half": "半",
        "fat": "胖",
        "ticket": "票",
        "wind": "风",
        "float": "飘",
        "door": "户",
        "square": "方",
        "house": "房",
        "wood": "木",
        "cross": "交",
        "school": "校",
        "father": "父",
        "ba": "巴",
        "dad": "爸"
      },
      "hints": [
        "先找搭档，把两块滑到同一条路。",
        "试一试发亮的方向。也可以按回转键重新摆。"
      ]
    },
    {
      "board": [
        [
          "door",
          "wind",
          null,
          "cross"
        ],
        [
          null,
          null,
          "father",
          null
        ],
        [
          "wood",
          null,
          "square",
          null
        ],
        [
          null,
          "ba",
          "ticket",
          null
        ]
      ],
      "walls": [
        5,
        11
      ],
      "pairs": [
        [
          "door",
          "square",
          "house"
        ],
        [
          "wood",
          "cross",
          "school"
        ],
        [
          "father",
          "ba",
          "dad"
        ],
        [
          "ticket",
          "wind",
          "float"
        ]
      ],
      "targets": [
        "house",
        "school",
        "dad",
        "float"
      ],
      "seconds": 0.22,
      "labels": {
        "mouth": "口",
        "few": "少",
        "quarrel": "吵",
        "king": "王",
        "see": "见",
        "now": "现",
        "nail": "丁",
        "page": "页",
        "top": "顶",
        "moon": "月",
        "half": "半",
        "fat": "胖",
        "ticket": "票",
        "wind": "风",
        "float": "飘",
        "door": "户",
        "square": "方",
        "house": "房",
        "wood": "木",
        "cross": "交",
        "school": "校",
        "father": "父",
        "ba": "巴",
        "dad": "爸"
      },
      "hints": [
        "先找搭档，把两块滑到同一条路。",
        "试一试发亮的方向。也可以按回转键重新摆。"
      ]
    }
  ]
}));

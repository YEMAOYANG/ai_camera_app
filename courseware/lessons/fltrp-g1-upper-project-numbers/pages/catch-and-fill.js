K.ready({"title": "接贴图，补满两格", "sub": "方向键接贴图，换篮键选空格。"});

K.game(K.gameTemplates.orchardCatch({
  "art": {
    "backdrop": "__IMG:project-stage__",
    "sticker": "__IMG:project-sticker__",
    "frames": [
      "__IMG:project-cart__"
    ],
    "icons": {
      "fruit": "__IMG:paper-star__"
    }
  },
  "voiceLead": true,
  "doneText": "两张拼贴都补好了！",
  "cues": [
    {
      "goal": "catch-two-three",
      "hint": "catch-hint",
      "hint2": "catch-help",
      "praise": "catch-good"
    },
    {
      "goal": "catch-four-five",
      "hint": "catch-hint",
      "hint2": "catch-help",
      "praise": "catch-good"
    },
    {
      "goal": "catch-seven-eight",
      "hint": "catch-hint",
      "hint2": "catch-help",
      "praise": "catch-good"
    }
  ],
  "levels": [
    {
      "capacity": [
        2,
        3
      ],
      "batches": [
        [
          2,
          0
        ],
        [
          3,
          2
        ]
      ],
      "seconds": 4.0,
      "catchRadius": 126,
      "wind": 0,
      "hints": [
        "先看亮线，再把小车开到亮线上。",
        "车慢一点。数一数，篮里还有几个空位？"
      ]
    },
    {
      "capacity": [
        4,
        5
      ],
      "batches": [
        [
          2,
          1
        ],
        [
          3,
          0
        ],
        [
          2,
          2
        ],
        [
          2,
          1
        ]
      ],
      "seconds": 3.35,
      "catchRadius": 107,
      "wind": 28,
      "hints": [
        "先看亮线，再把小车开到亮线上。",
        "车慢一点。数一数，篮里还有几个空位？"
      ]
    },
    {
      "capacity": [
        7,
        8
      ],
      "batches": [
        [
          4,
          0
        ],
        [
          3,
          2
        ],
        [
          2,
          1
        ],
        [
          4,
          2
        ],
        [
          2,
          0
        ]
      ],
      "seconds": 2.9,
      "catchRadius": 90,
      "wind": 70,
      "hints": [
        "先看亮线，再把小车开到亮线上。",
        "车慢一点。数一数，篮里还有几个空位？"
      ]
    }
  ]
}));

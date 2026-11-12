K.ready({"title": "接鞋配成双", "sub": "用小车接鞋，给单只鞋配伙伴。"});

K.game(K.gameTemplates.orchardCatch({
  "art": {
    "backdrop": "__IMG:shore-stage__",
    "sticker": "__IMG:shore-sticker__",
    "frames": [
      "__IMG:shore-cart__"
    ],
    "icons": {
      "fruit": "__IMG:shore-shoe__"
    }
  },
  "voiceLead": true,
  "doneText": "鞋子配成双了！",
  "cues": [
    {
      "goal": "round-one",
      "hint": "pair-hint",
      "hint2": "pair-help",
      "praise": "pair-good"
    },
    {
      "goal": "round-two",
      "hint": "pair-hint",
      "hint2": "pair-help",
      "praise": "pair-good"
    },
    {
      "goal": "round-three",
      "hint": "pair-hint",
      "hint2": "pair-help",
      "praise": "pair-good"
    }
  ],
  "levels": [
    {
      "capacity": [
        2,
        1
      ],
      "batches": [
        [
          2,
          0
        ],
        [
          1,
          2
        ]
      ],
      "seconds": 4.0,
      "catchRadius": 129,
      "wind": 0,
      "hints": [
        "数一数空格，再接住整组。",
        "落得慢些了。给单只鞋找伙伴。"
      ]
    },
    {
      "capacity": [
        2,
        2
      ],
      "batches": [
        [
          1,
          2
        ],
        [
          2,
          0
        ],
        [
          1,
          1
        ]
      ],
      "seconds": 3.55,
      "catchRadius": 112,
      "wind": 29,
      "hints": [
        "数一数空格，再接住整组。",
        "落得慢些了。给单只鞋找伙伴。"
      ]
    },
    {
      "capacity": [
        2,
        2
      ],
      "batches": [
        [
          1,
          1
        ],
        [
          2,
          2
        ],
        [
          1,
          0
        ]
      ],
      "seconds": 2.95,
      "catchRadius": 98,
      "wind": 65,
      "hints": [
        "数一数空格，再接住整组。",
        "落得慢些了。给单只鞋找伙伴。"
      ]
    }
  ]
}));

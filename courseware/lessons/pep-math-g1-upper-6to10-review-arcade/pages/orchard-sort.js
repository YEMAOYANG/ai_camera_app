K.ready({"title": "整串果子进双篮", "sub": "移动小车接整串，两篮刚好填满。"});

K.game(K.gameTemplates.orchardCatch({
  "art": {
    "backdrop": "__IMG:garden__",
    "frames": [
      "__IMG:orchard-cart__"
    ],
    "icons": {
      "fruit": "__IMG:orchard-apple__"
    },
    "sticker": "__IMG:sticker__"
  },
  "voiceLead": true,
  "cues": [
    {
      "goal": "orchard-six",
      "hint": "orchard-hint",
      "hint2": "orchard-help",
      "praise": "orchard-good"
    },
    {
      "goal": "orchard-eight",
      "hint": "orchard-hint",
      "hint2": "orchard-help",
      "praise": "orchard-good"
    },
    {
      "goal": "orchard-ten",
      "hint": "orchard-hint",
      "hint2": "orchard-help",
      "praise": "orchard-good"
    }
  ],
  "doneText": "两只果篮正好填满啦！",
  "levels": [
    {
      "capacity": [
        2,
        4
      ],
      "batches": [
        [
          2,
          0
        ],
        [
          4,
          2
        ]
      ],
      "seconds": 4.3,
      "catchRadius": 125,
      "hints": [
        "看看发亮的落点。把小车开到果子下面。",
        "一串要一起进一个篮。空格不够就换篮，再试一次。"
      ]
    },
    {
      "capacity": [
        3,
        5
      ],
      "batches": [
        [
          2,
          0
        ],
        [
          3,
          1
        ],
        [
          3,
          2
        ]
      ],
      "seconds": 3.55,
      "catchRadius": 106,
      "hints": [
        "看看发亮的落点。把小车开到果子下面。",
        "一串要一起进一个篮。空格不够就换篮，再试一次。"
      ]
    },
    {
      "capacity": [
        4,
        6
      ],
      "batches": [
        [
          3,
          0
        ],
        [
          2,
          2
        ],
        [
          1,
          1
        ],
        [
          4,
          2
        ]
      ],
      "seconds": 2.75,
      "catchRadius": 90,
      "wind": 90,
      "hints": [
        "看看发亮的落点。把小车开到果子下面。",
        "一串要一起进一个篮。空格不够就换篮，再试一次。"
      ]
    }
  ]
}));

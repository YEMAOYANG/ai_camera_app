K.ready({"title": "开小车送拼贴", "sub": "先听取哪一组，再听送到哪一格。"});

K.game(K.gameTemplates.listenDelivery({
  "art": {
    "backdrop": "__IMG:project-stage__",
    "sticker": "__IMG:project-sticker__",
    "frames": [
      "__IMG:project-cart__",
      "__IMG:project-cart-run__",
      "__IMG:project-traffic__"
    ],
    "icons": {
      "cargo-book-2": "__IMG:cargo-book-2__",
      "cargo-book-4": "__IMG:cargo-book-4__",
      "cargo-leaf-9": "__IMG:cargo-leaf-9__",
      "cargo-ruler-4": "__IMG:cargo-ruler-4__",
      "cargo-ruler-5": "__IMG:cargo-ruler-5__",
      "cargo-ruler-6": "__IMG:cargo-ruler-6__",
      "cargo-ruler-7": "__IMG:cargo-ruler-7__",
      "cargo-star-10": "__IMG:cargo-star-10__",
      "cargo-star-9": "__IMG:cargo-star-9__",
      "display-book-2": "__IMG:display-book-2__",
      "display-book-4": "__IMG:display-book-4__",
      "display-leaf-9": "__IMG:display-leaf-9__",
      "display-ruler-4": "__IMG:display-ruler-4__",
      "display-ruler-5": "__IMG:display-ruler-5__",
      "display-ruler-6": "__IMG:display-ruler-6__",
      "display-ruler-7": "__IMG:display-ruler-7__",
      "display-star-10": "__IMG:display-star-10__",
      "display-star-9": "__IMG:display-star-9__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "doneText": "拼贴送到展板上啦！",
  "cues": [
    {
      "goal": "pick-books-two",
      "hint": "deliver-hint",
      "hint2": "deliver-help",
      "praise": "deliver-good",
      "steps": [
        "pick-books-two",
        "send-two"
      ]
    },
    {
      "goal": "pick-rulers-five",
      "hint": "deliver-hint",
      "hint2": "deliver-help",
      "praise": "deliver-good",
      "steps": [
        "pick-rulers-five",
        "send-five",
        "pick-rulers-six",
        "send-six"
      ]
    },
    {
      "goal": "pick-leaves-nine",
      "hint": "deliver-hint",
      "hint2": "deliver-help",
      "praise": "deliver-good",
      "steps": [
        "pick-leaves-nine",
        "send-nine",
        "pick-stars-ten",
        "send-ten",
        "pick-rulers-seven",
        "send-seven"
      ]
    }
  ],
  "levels": [
    {
      "pickup": [
        [
          "cargo-book-2",
          3
        ],
        [
          "cargo-ruler-4",
          6
        ]
      ],
      "drop": [
        [
          "display-book-2",
          3
        ],
        [
          "display-ruler-4",
          6
        ]
      ],
      "orders": [
        [
          "cargo-book-2",
          "display-book-2"
        ]
      ],
      "lanes": [
        {
          "row": 2,
          "speed": 0.9,
          "spacing": 5.7,
          "phase": 0
        }
      ],
      "step": 0.33,
      "hints": [
        "先听取什么，再看那一组有几件。",
        "停一停，点重听。看发亮的图，再走。"
      ]
    },
    {
      "pickup": [
        [
          "cargo-ruler-5",
          2
        ],
        [
          "cargo-ruler-6",
          6
        ],
        [
          "cargo-book-4",
          8
        ]
      ],
      "drop": [
        [
          "display-ruler-5",
          2
        ],
        [
          "display-ruler-6",
          6
        ],
        [
          "display-book-4",
          8
        ]
      ],
      "orders": [
        [
          "cargo-ruler-5",
          "display-ruler-5"
        ],
        [
          "cargo-ruler-6",
          "display-ruler-6"
        ]
      ],
      "lanes": [
        {
          "row": 1,
          "speed": -1.2,
          "spacing": 4.6,
          "phase": 2
        },
        {
          "row": 3,
          "speed": 1.33,
          "spacing": 4.6,
          "phase": 1
        }
      ],
      "step": 0.26,
      "hints": [
        "先听取什么，再看那一组有几件。",
        "停一停，点重听。看发亮的图，再走。"
      ]
    },
    {
      "pickup": [
        [
          "cargo-leaf-9",
          1
        ],
        [
          "cargo-star-10",
          4
        ],
        [
          "cargo-ruler-7",
          7
        ],
        [
          "cargo-star-9",
          8
        ]
      ],
      "drop": [
        [
          "display-leaf-9",
          2
        ],
        [
          "display-star-10",
          4
        ],
        [
          "display-ruler-7",
          7
        ],
        [
          "display-star-9",
          8
        ]
      ],
      "orders": [
        [
          "cargo-leaf-9",
          "display-leaf-9"
        ],
        [
          "cargo-star-10",
          "display-star-10"
        ],
        [
          "cargo-ruler-7",
          "display-ruler-7"
        ]
      ],
      "lanes": [
        {
          "row": 1,
          "speed": 1.31,
          "spacing": 4.8,
          "phase": 0
        },
        {
          "row": 2,
          "speed": -1.51,
          "spacing": 4.8,
          "phase": 2
        },
        {
          "row": 3,
          "speed": 1.55,
          "spacing": 4.8,
          "phase": 4
        }
      ],
      "step": 0.22,
      "hints": [
        "先听取什么，再看那一组有几件。",
        "停一停，点重听。看发亮的图，再走。"
      ]
    }
  ]
}));

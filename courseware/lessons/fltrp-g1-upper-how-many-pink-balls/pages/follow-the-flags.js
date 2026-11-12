K.ready({"title": "彩球邮车去哪里？", "sub": "听口令拿彩球。等路空，再开到指定的旗子。"});

K.game(K.gameTemplates.listenDelivery({
  "art": {
    "backdrop": "__IMG:delivery-background__",
    "sticker": "__IMG:ball-sticker__",
    "frames": [
      "__IMG:delivery-cart__",
      "__IMG:delivery-cart-pop__",
      "__IMG:traffic-cart__"
    ],
    "icons": {
      "p1b2": "__IMG:group-p1b2__",
      "p2b1": "__IMG:group-p2b1__",
      "p2b2": "__IMG:group-p2b2__",
      "p3b1": "__IMG:group-p3b1__",
      "p4b1": "__IMG:group-p4b1__",
      "u2p3": "__IMG:group-u2p3__",
      "u3b1": "__IMG:group-u3b1__",
      "u3p2": "__IMG:group-u3p2__",
      "u4p1": "__IMG:group-u4p1__",
      "pink-flag": "__IMG:pink-flag__",
      "brown-flag": "__IMG:brown-flag__",
      "blue-flag": "__IMG:blue-flag__"
    }
  },
  "doneText": "彩球都到站啦！",
  "voiceLead": true,
  "stepVoiceLead": true,
  "cues": [
    {
      "steps": [
        "two-pink",
        "to-pink"
      ],
      "goal": "two-pink",
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-praise"
    },
    {
      "steps": [
        "three-pink",
        "to-blue",
        "three-blue",
        "to-pink"
      ],
      "goal": "three-pink",
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-praise"
    },
    {
      "steps": [
        "four-blue",
        "to-brown",
        "four-pink",
        "to-pink",
        "three-blue",
        "to-blue"
      ],
      "goal": "four-blue",
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-praise"
    }
  ],
  "levels": [
    {
      "pickup": [
        [
          "p2b1",
          3
        ],
        [
          "p1b2",
          6
        ]
      ],
      "drop": [
        [
          "pink-flag",
          3
        ],
        [
          "blue-flag",
          6
        ]
      ],
      "orders": [
        [
          "p2b1",
          "pink-flag"
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
        "再听一次，看是取球还是送货。",
        "看亮起的站，等路上有空再走。"
      ]
    },
    {
      "pickup": [
        [
          "p3b1",
          2
        ],
        [
          "p2b2",
          4
        ],
        [
          "u3b1",
          6
        ]
      ],
      "drop": [
        [
          "pink-flag",
          2
        ],
        [
          "blue-flag",
          4
        ],
        [
          "brown-flag",
          6
        ]
      ],
      "orders": [
        [
          "p3b1",
          "blue-flag"
        ],
        [
          "u3b1",
          "pink-flag"
        ]
      ],
      "lanes": [
        {
          "row": 1,
          "speed": 0.85,
          "spacing": 5.5,
          "phase": 1
        },
        {
          "row": 3,
          "speed": -1.0,
          "spacing": 5.6,
          "phase": 0
        }
      ],
      "step": 0.29,
      "hints": [
        "再听一次，看是取球还是送货。",
        "看亮起的站，等路上有空再走。"
      ]
    },
    {
      "pickup": [
        [
          "u4p1",
          1
        ],
        [
          "u3p2",
          3
        ],
        [
          "p4b1",
          5
        ],
        [
          "u2p3",
          7
        ]
      ],
      "drop": [
        [
          "pink-flag",
          2
        ],
        [
          "blue-flag",
          4
        ],
        [
          "brown-flag",
          6
        ]
      ],
      "orders": [
        [
          "u4p1",
          "brown-flag"
        ],
        [
          "p4b1",
          "pink-flag"
        ],
        [
          "u3p2",
          "blue-flag"
        ]
      ],
      "lanes": [
        {
          "row": 1,
          "speed": 0.9,
          "spacing": 5.8,
          "phase": 0
        },
        {
          "row": 2,
          "speed": -1.15,
          "spacing": 5.4,
          "phase": 1
        },
        {
          "row": 3,
          "speed": 1.2,
          "spacing": 5.7,
          "phase": 2
        }
      ],
      "step": 0.26,
      "hints": [
        "再听一次，看是取球还是送货。",
        "看亮起的站，等路上有空再走。"
      ]
    }
  ]
}));

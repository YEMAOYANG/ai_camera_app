K.ready({"title": "小车送对数字站", "sub": "先取货，再按计数器上的位置送货。"});

K.game(K.gameTemplates.listenDelivery({
  "art": {
    "backdrop": "__IMG:garden__",
    "sticker": "__IMG:sticker__",
    "frames": [
      "__IMG:rover__",
      "__IMG:rover-pop__",
      "__IMG:glider__"
    ],
    "icons": {
      "ab-five": "__IMG:ab-five__",
      "ab-four": "__IMG:ab-four__",
      "ab-one": "__IMG:ab-one__",
      "ab-ten": "__IMG:ab-ten__",
      "ab-three": "__IMG:ab-three__",
      "ab-two": "__IMG:ab-two__",
      "stick-bundle": "__IMG:stick-bundle__",
      "stick-loose-five": "__IMG:stick-loose-five__",
      "stick-loose-four": "__IMG:stick-loose-four__",
      "stick-loose-one": "__IMG:stick-loose-one__",
      "stick-loose-three": "__IMG:stick-loose-three__",
      "stick-loose-two": "__IMG:stick-loose-two__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "doneText": "数字站都收到啦！",
  "cues": [
    {
      "steps": [
        "pick-ten",
        "send-ten"
      ],
      "goal": "pick-ten",
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-good"
    },
    {
      "steps": [
        "pick-two",
        "send-two",
        "pick-ten",
        "send-ten"
      ],
      "goal": "pick-two",
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-good"
    },
    {
      "steps": [
        "pick-three",
        "send-three",
        "pick-ten",
        "send-ten",
        "pick-five",
        "send-five"
      ],
      "goal": "pick-three",
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-good"
    }
  ],
  "levels": [
    {
      "pickup": [
        [
          "stick-bundle",
          3
        ],
        [
          "stick-loose-one",
          6
        ]
      ],
      "drop": [
        [
          "ab-ten",
          3
        ],
        [
          "ab-one",
          6
        ]
      ],
      "orders": [
        [
          "stick-bundle",
          "ab-ten"
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
        "先看车装了没有，再重听这一步的口令。",
        "车慢下来了。看看发亮的站，等车道空了再走。"
      ]
    },
    {
      "pickup": [
        [
          "stick-bundle",
          2
        ],
        [
          "stick-loose-two",
          6
        ],
        [
          "stick-loose-four",
          8
        ]
      ],
      "drop": [
        [
          "ab-four",
          1
        ],
        [
          "ab-two",
          5
        ],
        [
          "ab-ten",
          7
        ]
      ],
      "orders": [
        [
          "stick-loose-two",
          "ab-two"
        ],
        [
          "stick-bundle",
          "ab-ten"
        ]
      ],
      "lanes": [
        {
          "row": 1,
          "speed": -1.25,
          "spacing": 4.6,
          "phase": 2
        },
        {
          "row": 3,
          "speed": 1.36,
          "spacing": 4.6,
          "phase": 1
        }
      ],
      "step": 0.26,
      "hints": [
        "先看车装了没有，再重听这一步的口令。",
        "车慢下来了。看看发亮的站，等车道空了再走。"
      ]
    },
    {
      "pickup": [
        [
          "stick-loose-five",
          1
        ],
        [
          "stick-bundle",
          4
        ],
        [
          "stick-loose-three",
          7
        ],
        [
          "stick-loose-four",
          8
        ]
      ],
      "drop": [
        [
          "ab-three",
          6
        ],
        [
          "ab-five",
          2
        ],
        [
          "ab-ten",
          4
        ],
        [
          "ab-four",
          8
        ]
      ],
      "orders": [
        [
          "stick-loose-three",
          "ab-three"
        ],
        [
          "stick-bundle",
          "ab-ten"
        ],
        [
          "stick-loose-five",
          "ab-five"
        ]
      ],
      "lanes": [
        {
          "row": 1,
          "speed": -1.8,
          "spacing": 3.9,
          "phase": 0.7
        },
        {
          "row": 2,
          "speed": 1.65,
          "spacing": 4,
          "phase": 2.2
        },
        {
          "row": 3,
          "speed": -1.6,
          "spacing": 3.9,
          "phase": 1.4
        }
      ],
      "step": 0.2,
      "hints": [
        "先看车装了没有，再重听这一步的口令。",
        "车慢下来了。看看发亮的站，等车道空了再走。"
      ]
    }
  ]
}));

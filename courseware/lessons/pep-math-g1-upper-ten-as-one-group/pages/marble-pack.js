K.ready({"title": "弹珠找同量图卡", "sub": "听口令，瞄准符合要求的数量图。"});

K.game(K.gameTemplates.magnetMarbles({
  "art": {
    "backdrop": "__IMG:marble-workshop__",
    "sticker": "__IMG:sticker__",
    "frames": [
      "__IMG:marble__"
    ],
    "icons": {
      "ab-one": "__IMG:ab-one__",
      "ab-ten": "__IMG:ab-ten__",
      "stick-bundle": "__IMG:stick-bundle__",
      "stick-bundle-five": "__IMG:stick-bundle-five__",
      "stick-bundle-one": "__IMG:stick-bundle-one__",
      "stick-bundle-six": "__IMG:stick-bundle-six__",
      "stick-bundle-three": "__IMG:stick-bundle-three__",
      "stick-bundle-two": "__IMG:stick-bundle-two__",
      "stick-loose-nine": "__IMG:stick-loose-nine__",
      "stick-loose-ten": "__IMG:stick-loose-ten__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "doneText": "图卡都配对啦！",
  "cues": [
    {
      "steps": [
        "loose-ten",
        "bundle-ten"
      ],
      "goal": "loose-ten",
      "hint": "marble-hint",
      "hint2": "marble-help",
      "praise": "marble-good"
    },
    {
      "steps": [
        "bundle-ten",
        "bundle-two",
        "bundle-six"
      ],
      "goal": "bundle-ten",
      "hint": "marble-hint",
      "hint2": "marble-help",
      "praise": "marble-good"
    },
    {
      "steps": [
        "bundle-five",
        "loose-ten",
        "counter-ten",
        "bundle-one"
      ],
      "goal": "bundle-five",
      "hint": "marble-hint",
      "hint2": "marble-help",
      "praise": "marble-good"
    }
  ],
  "levels": [
    {
      "queue": [
        "loose-ten",
        "bundle-ten"
      ],
      "pairs": [
        [
          "loose-ten",
          "stick-loose-ten"
        ],
        [
          "bundle-ten",
          "stick-bundle"
        ]
      ],
      "targets": [
        {
          "x": 365,
          "value": "stick-loose-nine"
        },
        {
          "x": 560,
          "value": "stick-loose-ten"
        },
        {
          "x": 773,
          "value": "stick-bundle"
        }
      ],
      "targetWidth": 174,
      "targetHeight": 118,
      "speed": 445,
      "drift": 5,
      "listenOnly": true,
      "hints": [
        "先听有没有一捆，再数旁边的散棒。",
        "亮起来的是这一回的图。数清了再瞄准。"
      ]
    },
    {
      "queue": [
        "bundle-ten",
        "bundle-two",
        "bundle-six"
      ],
      "pairs": [
        [
          "bundle-ten",
          "stick-bundle"
        ],
        [
          "bundle-two",
          "stick-bundle-two"
        ],
        [
          "bundle-six",
          "stick-bundle-six"
        ]
      ],
      "targets": [
        {
          "x": 363,
          "value": "stick-bundle-three"
        },
        {
          "x": 534,
          "value": "stick-bundle-two"
        },
        {
          "x": 704,
          "value": "stick-bundle"
        },
        {
          "x": 873,
          "value": "stick-bundle-six"
        }
      ],
      "targetWidth": 150,
      "targetHeight": 118,
      "speed": 485,
      "drift": 8,
      "listenOnly": true,
      "hints": [
        "先听有没有一捆，再数旁边的散棒。",
        "亮起来的是这一回的图。数清了再瞄准。"
      ]
    },
    {
      "queue": [
        "bundle-five",
        "loose-ten",
        "counter-ten",
        "bundle-one"
      ],
      "pairs": [
        [
          "bundle-five",
          "stick-bundle-five"
        ],
        [
          "loose-ten",
          "stick-loose-ten"
        ],
        [
          "counter-ten",
          "ab-ten"
        ],
        [
          "bundle-one",
          "stick-bundle-one"
        ]
      ],
      "targets": [
        {
          "x": 350,
          "value": "stick-loose-ten"
        },
        {
          "x": 496,
          "value": "ab-one"
        },
        {
          "x": 640,
          "value": "stick-bundle-one"
        },
        {
          "x": 785,
          "value": "ab-ten"
        },
        {
          "x": 931,
          "value": "stick-bundle-five"
        }
      ],
      "targetWidth": 122,
      "targetHeight": 118,
      "speed": 520,
      "drift": 10,
      "listenOnly": true,
      "hints": [
        "先听有没有一捆，再数旁边的散棒。",
        "亮起来的是这一回的图。数清了再瞄准。"
      ]
    }
  ]
}));

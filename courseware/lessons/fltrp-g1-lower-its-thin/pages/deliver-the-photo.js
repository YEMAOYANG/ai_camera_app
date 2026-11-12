K.ready({   "title": "开相机车送照片",   "sub": "听大小和颜色，取照片再送进展格。" });

K.game(K.gameTemplates.listenDelivery({
  "art": {
    "backdrop": "__IMG:farm-photo-stage__",
    "sticker": "__IMG:farm-camera-sticker__",
    "frames": [
      "__IMG:farm-rover__",
      "__IMG:farm-rover-flash__",
      "__IMG:farm-lens-ball__"
    ],
    "icons": {
      "black-big": "__IMG:farm-pair-black-big__",
      "black-little": "__IMG:farm-pair-black-little__",
      "pink-big": "__IMG:farm-pair-pink-big__",
      "pink-little": "__IMG:farm-pair-pink-little__",
      "one-black": "__IMG:farm-one-black-little__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "cues": [
    {
      "goal": "pick-black-little",
      "steps": [
        "pick-black-little",
        "drop-black-little"
      ],
      "hint": "drive-hint",
      "hint2": "drive-help",
      "praise": "drive-good"
    },
    {
      "goal": "pick-pink-little",
      "steps": [
        "pick-pink-little",
        "drop-pink-little",
        "pick-black-big",
        "drop-black-big"
      ],
      "hint": "drive-hint",
      "hint2": "drive-help",
      "praise": "drive-good"
    },
    {
      "goal": "pick-black-little",
      "steps": [
        "pick-black-little",
        "drop-black-little",
        "pick-pink-big",
        "drop-pink-big",
        "pick-black-big",
        "drop-black-big"
      ],
      "hint": "drive-hint",
      "hint2": "drive-help",
      "praise": "drive-good"
    }
  ],
  "levels": [
    {
      "pickup": [
        [
          "black-big",
          1
        ],
        [
          "black-little",
          3
        ],
        [
          "pink-little",
          6
        ]
      ],
      "drop": [
        [
          "black-big",
          1
        ],
        [
          "black-little",
          3
        ],
        [
          "pink-little",
          6
        ]
      ],
      "orders": [
        [
          "black-little",
          "black-little"
        ]
      ],
      "step": 0.33,
      "lanes": [
        {
          "row": 2,
          "speed": 0.89,
          "spacing": 5.8,
          "phase": 0
        }
      ],
      "hints": [
        "先重听，回想刚才听到的两条线索。",
        "看同一张照片，先比大小，再对颜色。"
      ]
    },
    {
      "pickup": [
        [
          "black-big",
          2
        ],
        [
          "pink-little",
          6
        ],
        [
          "pink-big",
          8
        ]
      ],
      "drop": [
        [
          "black-big",
          3
        ],
        [
          "pink-little",
          6
        ],
        [
          "pink-big",
          8
        ]
      ],
      "orders": [
        [
          "pink-little",
          "pink-little"
        ],
        [
          "black-big",
          "black-big"
        ]
      ],
      "step": 0.26,
      "lanes": [
        {
          "row": 1,
          "speed": -1.19,
          "spacing": 4.6,
          "phase": 2
        },
        {
          "row": 3,
          "speed": 1.3,
          "spacing": 4.7,
          "phase": 1
        }
      ],
      "hints": [
        "先重听，回想刚才听到的两条线索。",
        "看同一张照片，先比大小，再对颜色。"
      ]
    },
    {
      "pickup": [
        [
          "pink-big",
          1
        ],
        [
          "black-little",
          4
        ],
        [
          "one-black",
          7
        ],
        [
          "black-big",
          8
        ]
      ],
      "drop": [
        [
          "pink-big",
          2
        ],
        [
          "black-little",
          4
        ],
        [
          "one-black",
          7
        ],
        [
          "black-big",
          8
        ]
      ],
      "orders": [
        [
          "black-little",
          "black-little"
        ],
        [
          "pink-big",
          "pink-big"
        ],
        [
          "black-big",
          "black-big"
        ]
      ],
      "step": 0.22,
      "lanes": [
        {
          "row": 1,
          "speed": 1.3,
          "spacing": 4.8,
          "phase": 0
        },
        {
          "row": 2,
          "speed": -1.53,
          "spacing": 4.8,
          "phase": 2
        },
        {
          "row": 3,
          "speed": 1.57,
          "spacing": 4.8,
          "phase": 4
        }
      ],
      "hints": [
        "先重听，回想刚才听到的两条线索。",
        "看同一张照片，先比大小，再对颜色。"
      ]
    }
  ],
  "doneText": "农场的照片都挂起来啦！"
}));

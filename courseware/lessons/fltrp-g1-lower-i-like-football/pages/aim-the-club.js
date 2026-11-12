K.ready({"title": "听谁在说，瞄准报名图", "sub": "听发话者和运动，再调方向发射。"});

K.game(K.gameTemplates.magnetMarbles({
  "art": {
    "backdrop": "__IMG:sport-stage__",
    "sticker": "__IMG:sport-sticker__",
    "frames": [
      "__IMG:sport-bubble__"
    ],
    "icons": {
      "we-foot": "__IMG:sport-we-football__",
      "they-foot": "__IMG:sport-they-football__",
      "i-basket": "__IMG:sport-i-basketball__",
      "we-ping": "__IMG:sport-we-ping__",
      "they-ping": "__IMG:sport-they-ping__",
      "they-basket": "__IMG:sport-they-basketball__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "doneText": "报名照片找对啦！",
  "cues": [
    {
      "goal": "we-foot",
      "steps": [
        "we-foot",
        "they-foot"
      ],
      "hint": "b-hint",
      "hint2": "b-help",
      "praise": "b-good"
    },
    {
      "goal": "i-basket",
      "steps": [
        "i-basket",
        "we-ping",
        "they-ping"
      ],
      "hint": "b-hint",
      "hint2": "b-help",
      "praise": "b-good"
    },
    {
      "goal": "they-basket",
      "steps": [
        "they-basket",
        "we-foot",
        "they-ping",
        "i-basket"
      ],
      "hint": "b-hint",
      "hint2": "b-help",
      "praise": "b-good"
    }
  ],
  "levels": [
    {
      "targets": [
        {
          "x": 407,
          "value": "we-foot"
        },
        {
          "x": 640,
          "value": "they-foot"
        }
      ],
      "queue": [
        "we-foot",
        "they-foot"
      ],
      "pairs": [
        [
          "we-foot",
          "we-foot"
        ],
        [
          "they-foot",
          "they-foot"
        ]
      ],
      "speed": 414,
      "drift": 5,
      "targetWidth": 200,
      "targetHeight": 128,
      "listenOnly": true,
      "hints": [
        "找话筒在哪个人上方，再听是哪项运动。",
        "靶慢了些。对着发亮的照片，顺着虚线瞄。"
      ]
    },
    {
      "targets": [
        {
          "x": 390,
          "value": "they-ping"
        },
        {
          "x": 640,
          "value": "i-basket"
        },
        {
          "x": 890,
          "value": "we-ping"
        }
      ],
      "queue": [
        "i-basket",
        "we-ping",
        "they-ping"
      ],
      "pairs": [
        [
          "i-basket",
          "i-basket"
        ],
        [
          "we-ping",
          "we-ping"
        ],
        [
          "they-ping",
          "they-ping"
        ]
      ],
      "speed": 474,
      "drift": 10,
      "targetWidth": 192,
      "targetHeight": 128,
      "listenOnly": true,
      "hints": [
        "找话筒在哪个人上方，再听是哪项运动。",
        "靶慢了些。对着发亮的照片，顺着虚线瞄。"
      ]
    },
    {
      "targets": [
        {
          "x": 325,
          "value": "they-ping"
        },
        {
          "x": 535,
          "value": "they-basket"
        },
        {
          "x": 745,
          "value": "we-foot"
        },
        {
          "x": 955,
          "value": "i-basket"
        }
      ],
      "queue": [
        "they-basket",
        "we-foot",
        "they-ping",
        "i-basket"
      ],
      "pairs": [
        [
          "they-basket",
          "they-basket"
        ],
        [
          "we-foot",
          "we-foot"
        ],
        [
          "they-ping",
          "they-ping"
        ],
        [
          "i-basket",
          "i-basket"
        ]
      ],
      "speed": 545,
      "drift": 13,
      "targetWidth": 184,
      "targetHeight": 128,
      "listenOnly": true,
      "hints": [
        "找话筒在哪个人上方，再听是哪项运动。",
        "靶慢了些。对着发亮的照片，顺着虚线瞄。"
      ]
    }
  ]
}));

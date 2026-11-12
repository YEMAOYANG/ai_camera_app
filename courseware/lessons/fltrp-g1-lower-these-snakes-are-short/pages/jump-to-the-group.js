K.ready({"title": "沿着动物园的口令跳", "sub": "听完当前一句，再跑跳到那一站。"});

K.game(K.gameTemplates.platformHop({
  "art": {
    "backdrop": "__IMG:zoo-stage__",
    "sticker": "__IMG:zoo-bot__",
    "frames": [
      "__IMG:zoo-bot__",
      "__IMG:zoo-bot-walk__",
      "__IMG:zoo-bot-jump__"
    ],
    "icons": {
      "short": "__IMG:zoo-short-group__",
      "long": "__IMG:zoo-long-group__",
      "tall": "__IMG:zoo-tall-group__",
      "low": "__IMG:zoo-low-group__",
      "big": "__IMG:zoo-big-group__",
      "small": "__IMG:zoo-small-group__",
      "tiger": "__IMG:zoo-tiger-group__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "cues": [
    {
      "goal": "visit-short",
      "steps": [
        "visit-short",
        "visit-tall",
        "visit-big"
      ],
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-good"
    },
    {
      "goal": "visit-long",
      "steps": [
        "visit-long",
        "visit-tiger",
        "visit-big"
      ],
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-good"
    },
    {
      "goal": "visit-tall",
      "steps": [
        "visit-tall",
        "visit-long",
        "visit-small",
        "visit-tiger"
      ],
      "hint": "hop-hint",
      "hint2": "hop-help",
      "praise": "hop-good"
    }
  ],
  "doneText": "动物园的路线走完啦！",
  "levels": [
    {
      "platforms": [
        [
          291,
          538,
          126,
          "start"
        ],
        [
          85,
          511,
          134,
          "long"
        ],
        [
          489,
          511,
          134,
          "short"
        ],
        [
          682,
          473,
          132,
          "tall"
        ],
        [
          878,
          436,
          136,
          "big"
        ],
        [
          1044,
          474,
          132,
          "tiger"
        ]
      ],
      "route": [
        "short",
        "tall",
        "big"
      ],
      "speed": 282,
      "prompt": null,
      "hints": [
        "先重听。把这一句和脚下的图对上。",
        "先找动物，再看它在图里的特征。"
      ]
    },
    {
      "platforms": [
        [
          614,
          554,
          128,
          "start"
        ],
        [
          414,
          509,
          128,
          "long"
        ],
        [
          242,
          493,
          125,
          "low"
        ],
        [
          832,
          532,
          122,
          "short"
        ],
        [
          592,
          451,
          128,
          "tiger"
        ],
        [
          788,
          407,
          125,
          "big"
        ]
      ],
      "route": [
        "long",
        "tiger",
        "big"
      ],
      "speed": 304,
      "prompt": null,
      "hints": [
        "先重听。把这一句和脚下的图对上。",
        "先找动物，再看它在图里的特征。"
      ]
    },
    {
      "platforms": [
        [
          66,
          552,
          124,
          "start"
        ],
        [
          262,
          501,
          117,
          "tall"
        ],
        [
          448,
          451,
          117,
          "long"
        ],
        [
          652,
          413,
          116,
          "small"
        ],
        [
          854,
          372,
          114,
          "tiger"
        ],
        [
          271,
          573,
          114,
          "short"
        ],
        [
          860,
          526,
          116,
          "big"
        ]
      ],
      "route": [
        "tall",
        "long",
        "small",
        "tiger"
      ],
      "speed": 327,
      "prompt": null,
      "hints": [
        "先重听。把这一句和脚下的图对上。",
        "先找动物，再看它在图里的特征。"
      ]
    }
  ]
}));

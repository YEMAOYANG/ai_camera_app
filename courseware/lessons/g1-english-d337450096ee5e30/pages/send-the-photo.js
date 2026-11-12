K.ready({"title": "开车送照片", "sub": "先听说的是谁，取到照片再送进相册。"});

K.game(K.gameTemplates.listenDelivery({
  "art": {
    "backdrop": "__IMG:family-gallery-stage__",
    "sticker": "__IMG:gallery-sticker__",
    "frames": [
      "__IMG:gallery-van__",
      "__IMG:gallery-van__",
      "__IMG:gallery-lane-wagon__"
    ],
    "icons": {
      "gallery-doctor-man": "__IMG:gallery-doctor-man__",
      "gallery-doc-woman": "__IMG:gallery-doctor-woman__",
      "gallery-driver": "__IMG:gallery-driver__",
      "gallery-nurse": "__IMG:gallery-nurse__",
      "gallery-police": "__IMG:gallery-police__",
      "gallery-pupil": "__IMG:gallery-pupil__"
    }
  },
  "voiceLead": true,
  "stepVoiceLead": true,
  "doneText": "相册里的照片都到齐啦！",
  "cues": [
    {
      "goal": "pick-nurse",
      "steps": [
        "pick-nurse",
        "send-her"
      ],
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-good"
    },
    {
      "goal": "pick-doctor-woman",
      "steps": [
        "pick-doctor-woman",
        "send-her",
        "pick-doctor-man",
        "send-him"
      ],
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-good"
    },
    {
      "goal": "pick-driver",
      "steps": [
        "pick-driver",
        "send-him",
        "pick-police",
        "send-him",
        "pick-pupil",
        "send-pupil"
      ],
      "hint": "delivery-hint",
      "hint2": "delivery-help",
      "praise": "delivery-good"
    }
  ],
  "levels": [
    {
      "pickup": [
        [
          "gallery-nurse",
          3
        ],
        [
          "gallery-driver",
          6
        ]
      ],
      "drop": [
        [
          "gallery-nurse",
          3
        ],
        [
          "gallery-driver",
          6
        ]
      ],
      "orders": [
        [
          "gallery-nurse",
          "gallery-nurse"
        ]
      ],
      "lanes": [
        {
          "row": 2,
          "speed": 0.89,
          "spacing": 5.8,
          "phase": 0
        }
      ],
      "step": 0.33,
      "hints": [
        "先听说的是谁，再看这一张照片。",
        "点重听。看人物，也看手里的工具。"
      ]
    },
    {
      "pickup": [
        [
          "gallery-doc-woman",
          2
        ],
        [
          "gallery-doctor-man",
          6
        ],
        [
          "gallery-driver",
          8
        ]
      ],
      "drop": [
        [
          "gallery-doc-woman",
          2
        ],
        [
          "gallery-doctor-man",
          6
        ],
        [
          "gallery-driver",
          8
        ]
      ],
      "orders": [
        [
          "gallery-doc-woman",
          "gallery-doc-woman"
        ],
        [
          "gallery-doctor-man",
          "gallery-doctor-man"
        ]
      ],
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
      "step": 0.26,
      "hints": [
        "先听说的是谁，再看这一张照片。",
        "点重听。看人物，也看手里的工具。"
      ]
    },
    {
      "pickup": [
        [
          "gallery-driver",
          1
        ],
        [
          "gallery-police",
          4
        ],
        [
          "gallery-pupil",
          7
        ],
        [
          "gallery-nurse",
          8
        ]
      ],
      "drop": [
        [
          "gallery-driver",
          2
        ],
        [
          "gallery-police",
          4
        ],
        [
          "gallery-pupil",
          7
        ],
        [
          "gallery-nurse",
          8
        ]
      ],
      "orders": [
        [
          "gallery-driver",
          "gallery-driver"
        ],
        [
          "gallery-police",
          "gallery-police"
        ],
        [
          "gallery-pupil",
          "gallery-pupil"
        ]
      ],
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
      "step": 0.22,
      "hints": [
        "先听说的是谁，再看这一张照片。",
        "点重听。看人物，也看手里的工具。"
      ]
    }
  ]
}));

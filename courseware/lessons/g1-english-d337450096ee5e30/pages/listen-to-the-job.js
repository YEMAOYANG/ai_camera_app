K.ready({"title": "听词，把照片接进泡泡", "sub": "听到职业或身份，再对准那张照片。"});

K.game(K.gameTemplates.wordBubbles({
  "art": {
    "backdrop": "__IMG:family-gallery-stage__",
    "sticker": "__IMG:gallery-sticker__",
    "frames": [
      "__IMG:gallery-boat__",
      "__IMG:gallery-boat__"
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
  "doneText": "照片都找到啦！",
  "cues": [
    {
      "goal": "listen-nurse",
      "steps": [
        "listen-nurse",
        "listen-driver"
      ],
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-good"
    },
    {
      "goal": "listen-police",
      "steps": [
        "listen-police",
        "listen-pupil",
        "listen-doctor"
      ],
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-good"
    },
    {
      "goal": "listen-driver",
      "steps": [
        "listen-driver",
        "listen-doctor",
        "listen-nurse",
        "listen-pupil"
      ],
      "hint": "bubble-hint",
      "hint2": "bubble-help",
      "praise": "bubble-good"
    }
  ],
  "levels": [
    {
      "rounds": [
        {
          "target": "gallery-nurse",
          "cards": [
            "gallery-nurse",
            "gallery-driver"
          ]
        },
        {
          "target": "gallery-driver",
          "cards": [
            "gallery-nurse",
            "gallery-driver"
          ]
        }
      ],
      "drift": 8,
      "pace": 0.67,
      "tolerance": 62,
      "hints": [
        "先重听词，再看照片里的动作。",
        "亮起的是一张图。看手里的物件，再慢慢对准。"
      ]
    },
    {
      "rounds": [
        {
          "target": "gallery-police",
          "cards": [
            "gallery-pupil",
            "gallery-police",
            "gallery-doctor-man"
          ]
        },
        {
          "target": "gallery-pupil",
          "cards": [
            "gallery-driver",
            "gallery-police",
            "gallery-pupil"
          ]
        },
        {
          "target": "gallery-doctor-man",
          "cards": [
            "gallery-doctor-man",
            "gallery-nurse",
            "gallery-driver"
          ]
        }
      ],
      "drift": 21,
      "pace": 0.96,
      "tolerance": 55,
      "hints": [
        "先重听词，再看照片里的动作。",
        "亮起的是一张图。看手里的物件，再慢慢对准。"
      ]
    },
    {
      "rounds": [
        {
          "target": "gallery-driver",
          "cards": [
            "gallery-police",
            "gallery-nurse",
            "gallery-driver"
          ]
        },
        {
          "target": "gallery-doc-woman",
          "cards": [
            "gallery-nurse",
            "gallery-doc-woman",
            "gallery-pupil"
          ]
        },
        {
          "target": "gallery-nurse",
          "cards": [
            "gallery-nurse",
            "gallery-doctor-man",
            "gallery-police"
          ]
        },
        {
          "target": "gallery-pupil",
          "cards": [
            "gallery-driver",
            "gallery-pupil",
            "gallery-doctor-man"
          ]
        }
      ],
      "drift": 38,
      "pace": 1.24,
      "tolerance": 49,
      "hints": [
        "先重听词，再看照片里的动作。",
        "亮起的是一张图。看手里的物件，再慢慢对准。"
      ]
    }
  ]
}));

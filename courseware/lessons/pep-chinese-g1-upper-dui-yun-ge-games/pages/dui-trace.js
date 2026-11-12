K.ready({"title":"沿着提笔路线开车","sub":"从小车处开始，按方向走完一笔。"});
const opening = K.$('#dui-opening').content.cloneNode(true);
for (const image of opening.querySelectorAll('img')) {
  image.addEventListener('error', () => {
    const fallback = image.dataset.fallback;
    if (fallback && image.getAttribute('src') !== fallback) image.src = fallback;
    else image.hidden = true;
  });
}
K.$('#ready .card').prepend(opening);

const game = K.gameTemplates.trace({
  "goalHeight": 90,
  "doneText": "从起点出发，照顺序写完了虫字。",
  "finishMark": "<img class=\"dui-reward\" alt=\"描笔奖章\" src='__IMG:dui-backup-trace-car__'>",
  "narration": [
    {
      "goal": "dui-p09-level1-goal",
      "hint": "dui-p09-hint",
      "hint2": "dui-p09-level1-hint2",
      "praise": "dui-p09-praise"
    },
    {
      "goal": "dui-p09-level2-goal",
      "hint": "dui-p09-hint",
      "hint2": "dui-p09-later-hint2",
      "praise": "dui-p09-praise"
    },
    {
      "goal": "dui-p09-level3-goal",
      "hint": "dui-p09-hint",
      "hint2": "dui-p09-later-hint2",
      "praise": "dui-p09-praise"
    }
  ],
  "levels": [
    {
      "name": "一笔提",
      "rounds": [
        {
          "goal": "提",
          "strokes": [
            [
              [
                506,
                515
              ],
              [
                774,
                399
              ]
            ]
          ],
          "gridBox": [
            640,
            455,
            390
          ],
          "background": {
            "image": "__IMG:trace-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "imageBox": [
            640,
            458,
            1100,
            463
          ],
          "car": {
            "image": "__IMG:trace-car__",
            "fallback": {
              "image": "__IMG:dui-backup-trace-car__",
              "fallback": "车"
            }
          },
          "corridor": 62,
          "hint": "回到小车边，找准起点。",
          "hint2": "沿亮起的一段走到底，走完抬手。",
          "success": "提笔走完啦！"
        }
      ]
    },
    {
      "name": "续写三笔",
      "rounds": [
        {
          "goal": "虫",
          "strokes": [
            [
              [
                639,
                312
              ],
              [
                639,
                527
              ]
            ],
            [
              [
                521,
                553
              ],
              [
                717,
                514
              ]
            ],
            [
              [
                702,
                478
              ],
              [
                755,
                546
              ]
            ]
          ],
          "gridBox": [
            640,
            455,
            390
          ],
          "background": {
            "image": "__IMG:trace-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "imageBox": [
            640,
            458,
            1100,
            463
          ],
          "car": {
            "image": "__IMG:trace-car__",
            "fallback": {
              "image": "__IMG:dui-backup-trace-car__",
              "fallback": "车"
            }
          },
          "corridor": 51,
          "hint": "回到小车边，找准起点。",
          "hint2": "沿亮起的一段走到底，走完抬手。",
          "success": "末三笔按顺序走完啦！",
          "prefill": [
            [
              [
                557,
                352
              ],
              [
                557,
                430
              ]
            ],
            [
              [
                557,
                352
              ],
              [
                723,
                352
              ],
              [
                723,
                430
              ]
            ],
            [
              [
                557,
                430
              ],
              [
                723,
                430
              ]
            ]
          ]
        }
      ]
    },
    {
      "name": "挑战六笔",
      "rounds": [
        {
          "goal": "虫",
          "strokes": [
            [
              [
                557,
                352
              ],
              [
                557,
                430
              ]
            ],
            [
              [
                557,
                352
              ],
              [
                723,
                352
              ],
              [
                723,
                430
              ]
            ],
            [
              [
                557,
                430
              ],
              [
                723,
                430
              ]
            ],
            [
              [
                639,
                312
              ],
              [
                639,
                527
              ]
            ],
            [
              [
                521,
                553
              ],
              [
                717,
                514
              ]
            ],
            [
              [
                702,
                478
              ],
              [
                755,
                546
              ]
            ]
          ],
          "gridBox": [
            640,
            455,
            390
          ],
          "background": {
            "image": "__IMG:trace-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "imageBox": [
            640,
            458,
            1100,
            463
          ],
          "car": {
            "image": "__IMG:trace-car__",
            "fallback": {
              "image": "__IMG:dui-backup-trace-car__",
              "fallback": "车"
            }
          },
          "corridor": 43,
          "hint": "回到小车边，找准起点。",
          "hint2": "沿亮起的一段走到底，走完抬手。",
          "success": "虫字六笔都走完啦！"
        }
      ]
    }
  ]
});
K.game(game);

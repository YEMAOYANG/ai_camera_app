K.ready({"title":"接住对拍搭档","sub":"看上方的图，左右移动篮子接同类搭档。"});
const opening = K.$('#dui-opening').content.cloneNode(true);
for (const image of opening.querySelectorAll('img')) {
  image.addEventListener('error', () => {
    const fallback = image.dataset.fallback;
    if (fallback && image.getAttribute('src') !== fallback) image.src = fallback;
    else image.hidden = true;
  });
}
K.$('#ready .card').prepend(opening);

const game = K.gameTemplates.parachute({
  "goalHeight": 112,
  "doneText": "看图分好类，六个搭档都接住了。",
  "finishMark": "<img class=\"dui-reward\" alt=\"接图奖章\" src='__IMG:dui-backup-catch-basket__'>",
  "narration": [
    {
      "goal": "dui-p06-level1-goal",
      "hint": "dui-p06-hint",
      "hint2": "dui-p06-hint2",
      "praise": "dui-p06-praise"
    },
    {
      "goal": "dui-p06-level2-goal",
      "hint": "dui-p06-hint",
      "hint2": "dui-p06-hint2",
      "praise": "dui-p06-praise"
    },
    {
      "goal": "dui-p06-level3-goal",
      "hint": "dui-p06-hint",
      "hint2": "dui-p06-hint2",
      "praise": "dui-p06-praise"
    }
  ],
  "levels": [
    {
      "name": "两张图",
      "rounds": [
        {
          "goal": {
            "image": "__IMG:flower__",
            "fallback": {
              "image": "__IMG:dui-backup-flower__",
              "fallback": "花"
            }
          },
          "options": [
            {
              "image": "__IMG:bird__",
              "fallback": {
                "image": "__IMG:dui-backup-bird__",
                "fallback": "鸟"
              }
            },
            {
              "image": "__IMG:tree__",
              "fallback": {
                "image": "__IMG:dui-backup-tree__",
                "fallback": "树"
              }
            }
          ],
          "answer": 1,
          "speed": 90,
          "catchRadius": 100,
          "hint": "再看看上面的图，想想它是哪一类。",
          "hint2": "图卡慢下来啦，找和上面同类的一张。",
          "background": {
            "image": "__IMG:catch-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "basket": {
            "image": "__IMG:catch-basket__",
            "fallback": {
              "image": "__IMG:dui-backup-catch-basket__",
              "fallback": "篮"
            }
          },
          "success": "接住同类搭档啦！"
        },
        {
          "goal": {
            "image": "__IMG:wind__",
            "fallback": {
              "image": "__IMG:dui-backup-wind__",
              "fallback": "风"
            }
          },
          "options": [
            {
              "image": "__IMG:rain__",
              "fallback": {
                "image": "__IMG:dui-backup-rain__",
                "fallback": "雨"
              }
            },
            {
              "image": "__IMG:insect__",
              "fallback": {
                "image": "__IMG:dui-backup-insect__",
                "fallback": "虫"
              }
            }
          ],
          "answer": 0,
          "speed": 90,
          "catchRadius": 100,
          "hint": "再看看上面的图，想想它是哪一类。",
          "hint2": "图卡慢下来啦，找和上面同类的一张。",
          "background": {
            "image": "__IMG:catch-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "basket": {
            "image": "__IMG:catch-basket__",
            "fallback": {
              "image": "__IMG:dui-backup-catch-basket__",
              "fallback": "篮"
            }
          },
          "success": "接住同类搭档啦！"
        }
      ],
      "demoRounds": [
        {
          "goal": {
            "image": "__IMG:rain__",
            "fallback": {
              "image": "__IMG:dui-backup-rain__",
              "fallback": "雨"
            }
          },
          "options": [
            {
              "image": "__IMG:flower__",
              "fallback": {
                "image": "__IMG:dui-backup-flower__",
                "fallback": "花"
              }
            },
            {
              "image": "__IMG:wind__",
              "fallback": {
                "image": "__IMG:dui-backup-wind__",
                "fallback": "风"
              }
            }
          ],
          "answer": 1,
          "speed": 90,
          "catchRadius": 100,
          "hint": "再看看上面的图，想想它是哪一类。",
          "hint2": "图卡慢下来啦，找和上面同类的一张。",
          "background": {
            "image": "__IMG:catch-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "basket": {
            "image": "__IMG:catch-basket__",
            "fallback": {
              "image": "__IMG:dui-backup-catch-basket__",
              "fallback": "篮"
            }
          },
          "success": "接住同类搭档啦！"
        }
      ]
    },
    {
      "name": "三张图",
      "rounds": [
        {
          "goal": {
            "image": "__IMG:bird__",
            "fallback": {
              "image": "__IMG:dui-backup-bird__",
              "fallback": "鸟"
            }
          },
          "options": [
            {
              "image": "__IMG:rain__",
              "fallback": {
                "image": "__IMG:dui-backup-rain__",
                "fallback": "雨"
              }
            },
            {
              "image": "__IMG:flower__",
              "fallback": {
                "image": "__IMG:dui-backup-flower__",
                "fallback": "花"
              }
            },
            {
              "image": "__IMG:insect__",
              "fallback": {
                "image": "__IMG:dui-backup-insect__",
                "fallback": "虫"
              }
            }
          ],
          "answer": 2,
          "speed": 108,
          "catchRadius": 86,
          "hint": "再看看上面的图，想想它是哪一类。",
          "hint2": "图卡慢下来啦，找和上面同类的一张。",
          "background": {
            "image": "__IMG:catch-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "basket": {
            "image": "__IMG:catch-basket__",
            "fallback": {
              "image": "__IMG:dui-backup-catch-basket__",
              "fallback": "篮"
            }
          },
          "success": "接住同类搭档啦！"
        },
        {
          "goal": {
            "image": "__IMG:tree__",
            "fallback": {
              "image": "__IMG:dui-backup-tree__",
              "fallback": "树"
            }
          },
          "options": [
            {
              "image": "__IMG:insect__",
              "fallback": {
                "image": "__IMG:dui-backup-insect__",
                "fallback": "虫"
              }
            },
            {
              "image": "__IMG:flower__",
              "fallback": {
                "image": "__IMG:dui-backup-flower__",
                "fallback": "花"
              }
            },
            {
              "image": "__IMG:rain__",
              "fallback": {
                "image": "__IMG:dui-backup-rain__",
                "fallback": "雨"
              }
            }
          ],
          "answer": 1,
          "speed": 108,
          "catchRadius": 86,
          "hint": "再看看上面的图，想想它是哪一类。",
          "hint2": "图卡慢下来啦，找和上面同类的一张。",
          "background": {
            "image": "__IMG:catch-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "basket": {
            "image": "__IMG:catch-basket__",
            "fallback": {
              "image": "__IMG:dui-backup-catch-basket__",
              "fallback": "篮"
            }
          },
          "success": "接住同类搭档啦！"
        }
      ]
    },
    {
      "name": "四张图",
      "rounds": [
        {
          "goal": {
            "image": "__IMG:insect__",
            "fallback": {
              "image": "__IMG:dui-backup-insect__",
              "fallback": "虫"
            }
          },
          "options": [
            {
              "image": "__IMG:tree__",
              "fallback": {
                "image": "__IMG:dui-backup-tree__",
                "fallback": "树"
              }
            },
            {
              "image": "__IMG:bird__",
              "fallback": {
                "image": "__IMG:dui-backup-bird__",
                "fallback": "鸟"
              }
            },
            {
              "image": "__IMG:flower__",
              "fallback": {
                "image": "__IMG:dui-backup-flower__",
                "fallback": "花"
              }
            },
            {
              "image": "__IMG:wind__",
              "fallback": {
                "image": "__IMG:dui-backup-wind__",
                "fallback": "风"
              }
            }
          ],
          "answer": 1,
          "speed": 124,
          "catchRadius": 76,
          "hint": "再看看上面的图，想想它是哪一类。",
          "hint2": "图卡慢下来啦，找和上面同类的一张。",
          "background": {
            "image": "__IMG:catch-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "basket": {
            "image": "__IMG:catch-basket__",
            "fallback": {
              "image": "__IMG:dui-backup-catch-basket__",
              "fallback": "篮"
            }
          },
          "success": "接住同类搭档啦！"
        },
        {
          "goal": {
            "image": "__IMG:rain__",
            "fallback": {
              "image": "__IMG:dui-backup-rain__",
              "fallback": "雨"
            }
          },
          "options": [
            {
              "image": "__IMG:tree__",
              "fallback": {
                "image": "__IMG:dui-backup-tree__",
                "fallback": "树"
              }
            },
            {
              "image": "__IMG:bird__",
              "fallback": {
                "image": "__IMG:dui-backup-bird__",
                "fallback": "鸟"
              }
            },
            {
              "image": "__IMG:insect__",
              "fallback": {
                "image": "__IMG:dui-backup-insect__",
                "fallback": "虫"
              }
            },
            {
              "image": "__IMG:wind__",
              "fallback": {
                "image": "__IMG:dui-backup-wind__",
                "fallback": "风"
              }
            }
          ],
          "answer": 3,
          "speed": 124,
          "catchRadius": 76,
          "hint": "再看看上面的图，想想它是哪一类。",
          "hint2": "图卡慢下来啦，找和上面同类的一张。",
          "background": {
            "image": "__IMG:catch-scene__",
            "fallback": {
              "image": "__IMG:landscape__",
              "fallback": "山水"
            }
          },
          "basket": {
            "image": "__IMG:catch-basket__",
            "fallback": {
              "image": "__IMG:dui-backup-catch-basket__",
              "fallback": "篮"
            }
          },
          "success": "接住同类搭档啦！"
        }
      ]
    }
  ]
});

function paintRain(c, x, y, age) {
  c.save();
  c.strokeStyle = '#26749B';
  c.lineWidth = 4;
  c.lineCap = 'round';
  for (const [dx, offset] of [[-14, 0], [0, 13], [14, 28]]) {
    const py = y - 41 + (age * 38 + offset) % 38;
    c.beginPath();
    c.moveTo(x + dx, py);
    c.lineTo(x + dx - 3, py + 13);
    c.stroke();
  }
  c.restore();
}

const drawGame = game.draw;
game.draw = (g, c) => {
  drawGame(g, c);
  const { plan, round, world } = g.data;
  if (!world) return;
  const current = plan.rounds[round];
  if (current.goal?.image === '__IMG:rain__') paintRain(c, 640, 82, g.t);
  const rainIndex = current.options.findIndex(card => card.image === '__IMG:rain__');
  if (rainIndex >= 0 && !world.rest) {
    paintRain(c, world.centers[rainIndex], world.y, world.age);
  }
};
K.game(game);

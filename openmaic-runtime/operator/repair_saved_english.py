"""Repair the saved first-course artifact, never generate or publish a course.

The operator keeps the source alongside the proposal. Apply only via the
hash-bound saved-stage recovery command; locked quiz content is unchanged.
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'output/course-library-supply-2026-09-09/recovery'


def main():
    original = json.loads((FOLDER / 'english-original.json').read_text())
    repaired = copy.deepcopy(original)
    scenes = {s['id']: s for s in repaired['scenes']}
    first = scenes['scene-p1']
    elements = {e['id']: e for e in first['content']['canvas']['elements']}
    elements['text_qPzB3hll']['content'] = '<p style="font-size:24px;text-align:center">大写和小写，找朋友。</p><p style="font-size:22px;text-align:center">读一读单词，听开头。</p>'
    pairs = [
        ('text_VxsMmzNB', '欢迎来到竹影车站！今天来当字母侦探，先认字母，再听单词。'),
        ('text_B9LQJ4VZ', '看这张卡片，大写 I 和小写 i 是一对。小写 i 的上面有一个点。'),
        ('text_2frVfp8w', '再看大写 L，下面有一横；它的小写 l 是一根竖线。这两种写法是一对。'),
        ('text_Ltrp6etB', '这里是大写 P 和小写 p，都有一个小肚子。小写 p 的竖线伸到下面。'),
        ('text_pnTCJEDC', '最后看看大写 K 和小写 k，都有伸出来的两笔。记住这四对，接下来试着找朋友。'),
    ]
    for index, (element_id, text) in enumerate(pairs):
        first['actions'][index * 2]['elementId'] = element_id
        first['actions'][index * 2 + 1]['text'] = text

    game = scenes['scene-p2']
    game['content']['html'] = (Path(__file__).parent / 'english-letter-game.html').read_text()
    game['content']['widgetConfig']['scoring'] = {'correctPoints': 10}
    game['actions'] = [
        {'id': 'repair-p2-s1', 'type': 'speech', 'text': '看看上面的大写字母，再点下面的小写伙伴。我们刚认识了这四对，现在自己试一试。'},
        {'id': 'repair-p2-h1', 'type': 'widget_highlight', 'target': '#opt-l', 'content': '看清形状，再选择。'},
        {'id': 'repair-p2-s2', 'type': 'speech', 'text': '如果选错，看看下面的形状提示，再选一次。猜错不扣分，找到一对才会加十分。'},
        {'id': 'repair-p2-s3', 'type': 'speech', 'text': '选对以后，点下一张继续。找到四对以后，可以点重新开始再练一次。'},
    ]
    demo = scenes['scene-p3']
    demo['actions'][5]['text'] = '看绿色卡片上的小写 i：一竖一点。这就是大写 I 的小写伙伴。'
    demo['actions'][4]['elementId'] = 'shape_Zt-JxLxf'

    sound = scenes['scene-p5']
    sound['title'] = '跟着读一读，听单词开头'
    sound['content']['html'] = (Path(__file__).parent / 'english-sound-map.html').read_text()
    sound['content']['widgetConfig'] = {
        'type': 'diagram', 'diagramType': 'flowchart',
        'concept': '看字母，听单词开头的声音',
        'nodes': [{'id': 'letter-r', 'label': 'R r'}, {'id': 'word-rabbit', 'label': 'rabbit'},
                  {'id': 'letter-k', 'label': 'K k'}, {'id': 'word-key', 'label': 'key'}],
        'edges': [{'id': 'r-rabbit', 'from': 'letter-r', 'to': 'word-rabbit', 'label': '开头 /r/'},
                  {'id': 'k-key', 'from': 'letter-k', 'to': 'word-key', 'label': '开头 /k/'}],
        'description': '先跟老师读 rabbit 和 key，再用新单词练习；错误后有首字母提示，可以重试。',
    }
    sound['actions'] = [
        {'id': 'repair-p5-s1', 'type': 'speech', 'text': '先跟我读，rabbit，兔子。听开头，rabbit。嘴唇稍稍向前，声音连着出来。看，rabbit 的开头字母是小写 r，对应大写 R。'},
        {'id': 'repair-p5-h1', 'type': 'widget_highlight', 'target': '#word-rabbit', 'content': 'R r → rabbit'},
        {'id': 'repair-p5-s2', 'type': 'speech', 'text': '再跟我读，key，钥匙。这个开头很短，轻轻发出来，key。开头字母是小写 k，对应大写 K。字母的名字和它在单词里的声音，要分开听。'},
        {'id': 'repair-p5-h2', 'type': 'widget_highlight', 'target': '#word-key', 'content': 'K k → key'},
        {'id': 'repair-p5-s3', 'type': 'speech', 'text': '现在试试看。先选 R 或 K，再选一个单词。点确认以后，看看单词的第一个字母，检查开头有没有相同。'},
        {'id': 'repair-p5-a1', 'type': 'widget_annotation', 'target': '#confirm', 'content': '选好后，检查一下。'},
        {'id': 'repair-p5-s4', 'type': 'speech', 'text': '如果没选对，看看提示，把单词开头和上面的字母再比一比，然后换一个。练会以后点重新开始，还能再试一次。'},
    ]
    # Assessment IDs, choices, answers, order and explanations remain locked.
    for source, target in zip(original['scenes'], repaired['scenes']):
        assert source['id'] == target['id'] and source['order'] == target['order']
        if source['type'] == 'quiz':
            assert source['content'] == target['content']
    (FOLDER / 'english-repaired.json').write_text(json.dumps(repaired, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

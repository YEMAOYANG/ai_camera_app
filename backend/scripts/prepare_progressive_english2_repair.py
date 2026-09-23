"""Prepare the exact saved English second-set repair. No services or calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'output/progressive-preview/saved-stage-english-slot2'
SOURCE_JOB_SHA = 'a3fb84e1c4e1f16424aa255b9f035453109b7103a7d61c609cfcdff41aaec037'
SOURCE_SNAPSHOT_SHA = '907bea82a0aa310510c316ec72fa5f331804588253e8b3c9aed73187f8e26458'
SOURCE_AUDIT_SHA = '889a83532086a9ae6ea29ba637d5b7988e1b6ccd0bd821e05220526ff82fa5b1'
SCENE = 'scene-cPGuaKtTIrFf'
RESEARCH_SHA = '93f184a8186de0648aef2b3b9d36f6390960de6820503c256ce1a874f29d8166'
PREVIOUS_PROPOSAL_SHA = '1aa4a0cbeb3020a1a7a761c3379afd14bbb92e5d8f7034c2be5085ff35b439eb'
PREVIOUS_REPAIR_SHA = 'd1fd24bccc45ce0c0382dabdbc1f2378fa36d6c511cc132effb4c9fa22563785'

VIEW_REPLACEMENTS = [
    ('  #controls {', '  #view-status { flex-basis:100%; color:#e5e9f0; font-size:18px; line-height:1.4; text-align:center; }\n  #controls {'),
    ('<span class="visitors">visitors (游客们)</span></div>',
     '<span class="visitors">visitors (游客们)</span><br><strong>She greets them. 她问候他们。</strong></div>'),
    ('    <button id="reset3d" title="恢复视角" aria-label="恢复视角">↺ 恢复视角</button>',
     '    <button id="reset3d" title="恢复视角" aria-label="恢复视角">↺ 恢复视角</button>\n    <output id="view-status" aria-live="polite"></output>'),
    ('var s = 260 / (dist - q[2]);',
     'var focal = Math.min(canvas.width * 0.65, canvas.height * 1.1); var s = focal / (dist - q[2]);'),
    ('    ctx.clearRect(0, 0, canvas.width, canvas.height);',
     "    ctx.clearRect(0, 0, canvas.width, canvas.height);\n    document.getElementById('view-status').textContent = '视角：水平 ' + Math.round(((yaw * 180 / Math.PI) % 360 + 360) % 360) + '° / 仰角 ' + Math.round(pitch * 180 / Math.PI) + '° · 缩放 ' + Math.round(DEF.dist / dist * 100) + '%';"),
    ("""        if (pr.label){
          ctx.fillStyle = '#e5e9f0';
          ctx.font = 'bold 20px system-ui, sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(pr.label, pr.x, pr.y - pr.r - 6);
        }""", '        // Draw the two labels after geometry at separate edge anchors.'),
    ("""    });
  }

  var dragging = false""", """    });
    function drawLabel(text, world, side, color){
      var point = project(rotate(world));
      var x = side === 'left' ? 24 : canvas.width - 24;
      var y = Math.max(132, Math.min(canvas.height - 146, point[1] - 28));
      ctx.font = 'bold 20px system-ui, sans-serif';
      ctx.textAlign = side;
      var width = ctx.measureText(text).width;
      var edge = side === 'left' ? x + width + 8 : x - width - 8;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(point[0], point[1]);
      ctx.lineTo(edge, y - 6);
      ctx.stroke();
      ctx.fillStyle = 'rgba(10,15,28,0.94)';
      ctx.fillRect(side === 'left' ? x - 6 : x - width - 6, y - 24, width + 12, 32);
      ctx.fillStyle = color;
      ctx.fillText(text, x, y);
    }
    drawLabel('girl（女孩）', [-1.8, 2.85, 0.4], 'left', '#f9a8d4');
    drawLabel('visitors（游客们）', [1.37, 2.35, 0.27], 'right', '#93c5fd');
  }

  var dragging = false"""),
]
P1_LAYOUT = {
    'shape_bl0Qv5hK': {'top': (300, 280)},
    'text_Anq-0bH3': {'top': (314, 288), 'height': (58, 80),
        'content': ('<p style="font-size: 24px;"><span style="background-color: #fbbf24; padding: 2px 6px;">She</span> greets them. · 意为“她问候他们”</p>',
                    '<p style="font-size: 22px; margin: 0; line-height: 1.4;"><span style="background-color: #fbbf24; padding: 2px 6px;">She</span> greets them.</p><p style="font-size: 18px; margin: 0; line-height: 1.4;">意为“她问候他们”</p>')},
    'shape_9EM8tfYK': {'top': (405, 385)},
    'text_IXcBUrUi': {'top': (419, 393), 'height': (58, 80),
        'content': ('<p style="font-size: 24px;">They greet <span style="background-color: #fbbf24; padding: 2px 6px;">her</span>. · 意为“他们问候她”</p>',
                    '<p style="font-size: 22px; margin: 0; line-height: 1.4;">They greet <span style="background-color: #fbbf24; padding: 2px 6px;">her</span>.</p><p style="font-size: 18px; margin: 0; line-height: 1.4;">意为“他们问候她”</p>')},
    'shape_hojUHMtz': {'fill': ('#fbbf24', '#ffffff')},
    'shape_TeVkERil': {'fill': ('#fbbf24', '#ffffff')},
}


def visible_3d(html):
    for old, new in VIEW_REPLACEMENTS:
        assert html.count(old) == 1, 'Original 3D markup changed'
        html = html.replace(old, new)
    return html


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_once(name, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    path = BASE / name
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError('Existing proposal differs: ' + name)
    else:
        with path.open('xb') as stream:
            path.chmod(0o600)
            stream.write(raw)
    return sha(raw)


def write_reviewed_revision(name, value, previous_sha):
    """Keep the prior reviewed bytes before replacing only its local pointer."""
    recovery = ROOT / 'openmaic-runtime/.runtime/OpenMAIC/data/formal-saved-stage-recoveries/omformal_90ed56f8cb07a09d6c51296a'
    assert not (recovery / 'completion.json').exists() and not list(recovery.glob('complete*.claim'))
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    target = BASE / name
    old = target.read_bytes()
    if old == raw:
        return sha(raw)
    assert sha(old) == previous_sha, 'Unrecognized previous proposal: ' + name
    for content in (old, raw):
        archive = BASE / name.replace('.json', '-' + sha(content) + '.json')
        if archive.exists():
            assert archive.read_bytes() == content, 'Immutable revision archive changed'
        else:
            with archive.open('xb') as stream:
                archive.chmod(0o600)
                stream.write(content)
    temporary = target.with_suffix('.tmp')
    with temporary.open('xb') as stream:
        temporary.chmod(0o600)
        stream.write(raw)
    temporary.replace(target)
    return sha(raw)


def main():
    audit_raw = (BASE / 'source-audit.json').read_bytes()
    assert sha(audit_raw) == SOURCE_AUDIT_SHA, 'Source audit changed'
    audit = json.loads(audit_raw)
    assert audit['sourceJobSha256'] == SOURCE_JOB_SHA
    assert audit['sourceSnapshotSha256'] == SOURCE_SNAPSHOT_SHA
    source_raw = (BASE / 'source-document.json').read_bytes()
    assert sha(source_raw) == audit['sourceDocumentSha256']
    source = json.loads(source_raw)
    scenes = deepcopy(source['scenes'])
    target = next(s for s in scenes if s['id'] == SCENE)
    original = next(s for s in source['scenes'] if s['id'] == SCENE)
    old, new = 'girl (她)', 'girl（女孩）'
    assert original['content']['html'].count(old) == 2
    old_font, new_font = "ctx.font = 'bold 13px system-ui, sans-serif';", "ctx.font = 'bold 20px system-ui, sans-serif';"
    assert original['content']['html'].count(old_font) == 1
    target['content']['html'] = original['content']['html'].replace(old, new).replace(old_font, new_font)
    changes = [{'sceneId': SCENE, 'path': '/content/html',
                'oldText': old, 'newText': new, 'occurrences': 2,
                'sourceHtmlSha256': sha(original['content']['html'].encode()),
                'repairedHtmlSha256': sha(target['content']['html'].encode())},
               {'sceneId': SCENE, 'path': '/content/html',
                'oldText': old_font, 'newText': new_font, 'occurrences': 1}]
    research_raw = (BASE / 'research-citation-evidence.json').read_bytes()
    assert sha(research_raw) == RESEARCH_SHA, 'Saved research evidence changed'
    research = json.loads(research_raw)
    assert research['sessionId'] == audit['identity']['session']
    assert len(research['materials']) == 1
    material = research['materials'][0]
    assert material['session_id'] == research['sessionId'] and material['observedInSearch'] is True
    assert material['source_url'] == 'https://m.hujiang.com/en_lianghui/p307762/'
    assert material['title'] == '两会精神_英语语法入门:人称代词 _沪江英语'
    old_citation = '语法依据：沪江英语《英语语法入门：人称代词》'
    new_citation = old_citation + ' · ' + material['source_url']
    footer_ids = {'scene-p1': 'text_-0Vi6jPX', 'scene-p2': 'text_bmZRi5DE',
                  'scene-p6': 'text_49usmC9u'}
    for scene in scenes:
        if scene['id'] in footer_ids:
            element_id = footer_ids[scene['id']]
            element = next(e for e in scene['content']['canvas']['elements'] if e['id'] == element_id)
            assert element['content'].count(old_citation) == 1
            element['content'] = element['content'].replace(old_citation, new_citation)
            changes.append({'sceneId': scene['id'], 'elementId': element_id,
                            'path': '/content/canvas/elements/' + element_id + '/content',
                            'oldText': old_citation, 'newText': new_citation, 'occurrences': 1})
        elif scene['id'] == 'scene-p3':
            assert scene['content']['html'].count(old_citation) == 1
            scene['content']['html'] = scene['content']['html'].replace(old_citation, new_citation)
            changes.append({'sceneId': scene['id'], 'path': '/content/html',
                            'oldText': old_citation, 'newText': new_citation, 'occurrences': 1})
    p2 = next(s for s in scenes if s['id'] == 'scene-p2')
    narration = next(a for a in p2['actions'] if a['id'] == 'action_x9dqNVFA')
    assert narration['type'] == 'speech' and narration['text'].count('上节课') == 1
    old_narration = narration['text']
    narration['text'] = old_narration.replace('上节课', '刚才')
    changes.append({'sceneId': 'scene-p2', 'actionId': narration['id'],
                    'path': '/actions/' + narration['id'] + '/text',
                    'oldText': '上节课', 'newText': '刚才', 'occurrences': 1,
                    'sourceTextSha256': sha(old_narration.encode()),
                    'repairedTextSha256': sha(narration['text'].encode())})
    assert sum(c['occurrences'] for c in changes) == 8
    target['content']['html'] = visible_3d(target['content']['html'])
    changes[0]['repairedHtmlSha256'] = sha(target['content']['html'].encode())
    changes.extend({'sceneId': SCENE, 'path': '/content/html',
                    'oldText': old, 'newText': new, 'occurrences': 1,
                    'reason': 'Actual screenshot and button probe: visible geometry, separate labels and camera feedback'}
                   for old, new in VIEW_REPLACEMENTS)
    p1 = next(s for s in scenes if s['id'] == 'scene-p1')
    for element_id, fields in P1_LAYOUT.items():
        element = next(e for e in p1['content']['canvas']['elements'] if e['id'] == element_id)
        for field, (before, after) in fields.items():
            assert element[field] == before, 'Original p1 layout changed'
            element[field] = after
            changes.append({'sceneId': 'scene-p1', 'elementId': element_id,
                            'path': '/content/canvas/elements/' + element_id + '/' + field,
                            'oldValue': before, 'newValue': after,
                            'reason': 'Separate translation rows and remove duplicate non-pronoun highlights'})
    assert len(scenes) == 8
    for before, after in zip(source['scenes'], scenes):
        expected = deepcopy(before)
        if before['id'] == SCENE:
            expected['content']['html'] = visible_3d(before['content']['html'].replace(old, new).replace(old_font, new_font))
        if before['id'] == 'scene-p1':
            for element_id, fields in P1_LAYOUT.items():
                element = next(e for e in expected['content']['canvas']['elements'] if e['id'] == element_id)
                for field, (_, value) in fields.items():
                    element[field] = value
        if before['id'] in footer_ids:
            element = next(e for e in expected['content']['canvas']['elements'] if e['id'] == footer_ids[before['id']])
            element['content'] = element['content'].replace(old_citation, new_citation)
        elif before['id'] == 'scene-p3':
            expected['content']['html'] = expected['content']['html'].replace(old_citation, new_citation)
        if before['id'] == 'scene-p2':
            action = next(a for a in expected['actions'] if a['id'] == 'action_x9dqNVFA')
            action['text'] = action['text'].replace('上节课', '刚才')
        assert after == expected, 'Unapproved content, identity, order or narration change'
    speech = [a for s in scenes for a in s.get('actions', []) if a['type'] == 'speech']
    assert len(speech) == 36
    assert [s for s in scenes if s['type'] == 'quiz'] == [s for s in source['scenes'] if s['type'] == 'quiz']
    proposal_sha = write_reviewed_revision('repair-proposal.json', {'scenes': scenes}, PREVIOUS_PROPOSAL_SHA)
    manifest = {'jobId': audit['identity']['job'], 'sourceJobSha256': SOURCE_JOB_SHA,
                'sessionId': audit['identity']['session'], 'stageId': audit['identity']['stage'],
                'sourceSnapshotSha256': SOURCE_SNAPSHOT_SHA, 'repairPath': 'repair-proposal.json'}
    manifest_sha = write_once('manifest.json', manifest)
    repair = {'schemaVersion': 'mira.progressive-english2-saved-stage-proposal.v1',
              'sourceAuditSha256': SOURCE_AUDIT_SHA, 'sourceJobSha256': SOURCE_JOB_SHA,
              'sourceSnapshotSha256': SOURCE_SNAPSHOT_SHA,
              'sourceDocumentSha256': audit['sourceDocumentSha256'],
              'proposalSha256': proposal_sha, 'manifestSha256': manifest_sha,
              'changes': changes, 'researchEvidenceSha256': RESEARCH_SHA,
              'fetchedSource': {'title': material['title'], 'url': material['source_url'],
                                'materialId': material['id']},
              'previousProposalSha256': PREVIOUS_PROPOSAL_SHA,
              'previousRepairAuditSha256': PREVIOUS_REPAIR_SHA,
              'allOtherFieldsEqual': True, 'frozenQuizEqual': True,
              'speechIdsEqual': True, 'speechTextChanges': 1, 'speechCount': 36,
              'formalInputUnchanged': True, 'oldJobAndLedgerUnchanged': True,
              'priorFormalAudioRecordCount': 0, 'providerCalls': 0, 'databaseWrites': 0}
    repair_sha = write_reviewed_revision('repair-audit.json', repair, PREVIOUS_REPAIR_SHA)
    print(json.dumps({'status': 'proposal_prepared', 'proposalSha256': proposal_sha,
                      'manifestSha256': manifest_sha, 'repairAuditSha256': repair_sha,
                      'baselineTextReplacements': 8, 'viewHtmlReplacements': len(VIEW_REPLACEMENTS),
                      'p1LayoutFields': sum(len(v) for v in P1_LAYOUT.values()), 'speechCount': 36,
                      'providerCalls': 0, 'databaseWrites': 0}))


if __name__ == '__main__':
    main()

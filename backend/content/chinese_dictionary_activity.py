"""Bounded, narrated dictionary practice with explicit demonstration pages.

Letter, syllable and character choices are the targets being taught. An original
meaning picture remains visible; directions never require independent reading.
"""
from html import escape
import re

from content import textbook_activity_templates as t
from content.textbook_activity_ir import require


IDENTITY_FIELDS = ('character', 'uppercase', 'syllable', 'tone', 'demonstrationPage')


def tonal_syllable(syllable, tone):
    require(re.fullmatch('[a-z]+', syllable) is not None and type(tone) is int and 1 <= tone <= 4,
            'dictionary_tone_invalid')
    vowels = 'aeiou'
    index = next((syllable.index(v) for v in 'aoe' if v in syllable), None)
    if index is None:
        index = max((i for i,c in enumerate(syllable) if c in vowels), default=-1)
    require(index >= 0, 'dictionary_syllable_missing_vowel')
    marked = {'a':'āáǎà','e':'ēéěè','i':'īíǐì','o':'ōóǒò','u':'ūúǔù'}[syllable[index]][tone-1]
    return syllable[:index] + marked + syllable[index+1:]


def lookup_picture(kind, value, page=None, phonetic=None):
    require(kind in {'letter', 'syllable', 'entry'}, 'dictionary_picture_kind')
    require(isinstance(value, str) and 1 <= len(value) <= 15, 'dictionary_picture_value')
    require(page is None or type(page) is int and 1 <= page <= 999, 'dictionary_demo_page')
    label = {'letter': '大写首字母 ', 'syllable': '演示索引音节 ', 'entry': '演示正文条目 '}[kind] + value
    if page is not None:
        label += '，演示页码 ' + str(page)
    if phonetic is not None:
        require(kind == 'entry' and isinstance(phonetic,str) and 1 <= len(phonetic) <= 12,
                'dictionary_entry_phonetic_invalid')
        label += '，拼音 ' + phonetic
    body = ('<path d="M23 27Q78 12 110 31Q156 12 197 27V154Q154 141 110 158Q62 141 23 154Z" '
            'fill="#fff9e8" stroke="#aa956c" stroke-width="4"/>'
            '<path d="M110 33v123" stroke="#d7c8a5" stroke-width="2"/>'
            '<rect x="30" y="54" width="160" height="65" rx="8" fill="#f6f1dd"/>'
            '<text x="110" y="99" text-anchor="middle" font-family="Arial,KaiTi,STKaiti,serif" '
            'font-size="' + ('49' if kind == 'letter' else '35') + '" fill="#345d51">'
            + escape(value) + '</text>')
    if phonetic is not None:
        body += '<text x="110" y="51" text-anchor="middle" font-family="Arial,sans-serif" font-size="20" fill="#345d51">'+escape(phonetic)+'</text>'
    if page is not None:
        body += ('<text x="176" y="143" text-anchor="middle" font-family="Arial,sans-serif" '
                 'font-size="20" fill="#6c7963">' + str(page) + '</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 180" role="img" '
            'aria-label="' + escape(label, quote=True) + '"><title>' + escape(label)
            + '</title><rect width="220" height="180" rx="16" fill="#e9efdd"/>' + body + '</svg>')


def validate_scene(scene, assets, scope):
    expected = scope.get('dictionaryPracticeEntries', [])
    entries = scene.get('entries', [])
    require(1 <= len(entries) <= 12 and len(entries) == len(expected)
            and [{k: entry.get(k) for k in IDENTITY_FIELDS} for entry in entries] == expected
            and len({entry['character'] for entry in entries}) == len(entries)
            and scene.get('adapterId') == 'narrated_dictionary_steps_v1'
            and set(scene.get('activityGoalIds', [])) == {'dictionary_lookup'}
            and not any(k in scene for k in ('html', 'script', 'states')), 'dictionary_scope_changed')
    for entry in entries:
        require(re.fullmatch('[A-Z]', entry['uppercase']) is not None
                and re.fullmatch('[a-z]+', entry['syllable']) is not None
                and entry['uppercase'] == entry['syllable'][0].upper()
                and type(entry['tone']) is int and 1 <= entry['tone'] <= 4
                and type(entry['demonstrationPage']) is int and 1 <= entry['demonstrationPage'] <= 999,
                'dictionary_phonetic_identity_invalid')
        steps = entry.get('steps', [])
        require(len(steps) == 3 and [s.get('kind') for s in steps] == ['letter', 'syllable', 'entry'],
                'dictionary_steps_changed')
        for index, step in enumerate(steps):
            options = step.get('options', [])
            require(len(options) == 3 and len({o.get('assetId') for o in options}) == 3
                    and len({o.get('value') for o in options}) == 3
                    and step.get('targetAssetId') in {o['assetId'] for o in options},
                    'dictionary_distinct_choices_required')
            for option in options:
                require(assets.get(option['assetId']) == lookup_picture(step['kind'], option['value'], option.get('page'), option.get('phonetic')),
                        'dictionary_choice_picture_changed')
            target = next(o for o in options if o['assetId'] == step['targetAssetId'])
            require(index != 0 or target['value'] == entry['uppercase'], 'dictionary_letter_target_changed')
            require(index != 1 or target['value'] == entry['syllable'] and target.get('page') == entry['demonstrationPage'],
                    'dictionary_index_target_changed')
            require(index != 2 or target['value'] == entry['character'] and target.get('page') == entry['demonstrationPage'],
                    'dictionary_body_target_changed')
            require(index != 2 or target.get('phonetic') == tonal_syllable(entry['syllable'],entry['tone']),
                    'dictionary_tone_target_changed')


LOOKUP = r'''
const lookup=CONFIG;let entryIndex=0,stepIndex=0,ready=false,matched=false,finished=false;
const completed=new Set();
function current(){return lookup.entries[entryIndex].steps[stepIndex];}
function showPictureFeedback(button){button.insertAdjacentHTML('beforeend','<svg class="feedback-mark" viewBox="0 0 64 64" aria-label="这一步找对了"><circle cx="32" cy="32" r="28" fill="#588b79"/><path d="m16 32 11 11 22-24" fill="none" stroke="#fffdf5" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg>');}
function refreshControls(){document.querySelectorAll('[data-dictionary-choice]').forEach(b=>b.disabled=interactionBusy||!ready||matched||finished);document.getElementById('next').disabled=interactionBusy||!matched||finished;}
function show(){ready=false;matched=false;finished=false;document.querySelectorAll('[data-dictionary-source]').forEach((e,i)=>e.hidden=i!==entryIndex);document.querySelectorAll('[data-dictionary-step]').forEach(e=>e.hidden=Number(e.dataset.entry)!==entryIndex||Number(e.dataset.step)!==stepIndex);document.querySelectorAll('[data-dictionary-choice]').forEach(b=>{b.classList.remove('selected');const mark=b.querySelector('.feedback-mark');if(mark)mark.remove();});document.querySelectorAll('[data-route]').forEach((e,i)=>{e.classList.toggle('done',i<stepIndex);e.setAttribute('aria-label',i<stepIndex?'这个查找步骤已完成':'这个查找步骤还未完成');});document.querySelectorAll('[data-progress]').forEach((e,i)=>{e.classList.toggle('done',completed.has(i));e.setAttribute('aria-label',completed.has(i)?'这个字已找到':'这个字还未找到');});refreshControls();}
function begin(intro=false){run(async signal=>{if(intro)await narrate(lookup.intro,signal);await narrate(current().instructionCueId,signal);ready=true;});}
listen('start',()=>begin(true));listen('replay',()=>begin(false));
listen('reset',()=>{cancelOperation();entryIndex=0;stepIndex=0;completed.clear();show();begin(true);});
document.querySelectorAll('[data-dictionary-choice]').forEach(button=>listen(button.id,()=>{if(interactionBusy||!ready||matched||finished)return;const step=current();run(async signal=>{if(button.dataset.asset!==step.targetAssetId){await narrate(lookup.retry,signal);return;}button.classList.add('selected');showPictureFeedback(button);await narrate(step.matchCueId,signal);matched=true;});}));
listen('next',()=>{if(interactionBusy||!matched||finished)return;if(stepIndex<2){stepIndex++;show();begin();}else{completed.add(entryIndex);if(entryIndex<lookup.entries.length-1){entryIndex++;stepIndex=0;show();begin();}else run(async signal=>{await narrate(lookup.complete,signal);finished=true;document.querySelectorAll('[data-route]').forEach(e=>{e.classList.add('done');e.setAttribute('aria-label','这个查找步骤已完成');});document.querySelectorAll('[data-progress]').forEach(e=>{e.classList.add('done');e.setAttribute('aria-label','这个字已找到');});note.textContent='请和大人一起用真实字典再查一查。';});}});
function applyTeacherState(state){if(Object.keys(state).length!==1||!Number.isInteger(state.entryIndex)||state.entryIndex<0||state.entryIndex>=lookup.entries.length)return;assisted=true;cancelOperation();entryIndex=state.entryIndex;stepIndex=0;show();begin();}
show();
'''


def dictionary_scene(scene, assets):
    body = '<div class="lookup-header"><div class="lookup-source">'
    for i, entry in enumerate(scene['entries']):
        body += '<div data-dictionary-source'+(' hidden' if i else '')+'>'+assets[entry['sourceAssetId']]+'</div>'
    body += '</div><div class="lookup-route" aria-label="查字典的三个步骤">'
    for i, glyph in enumerate(('A', 'a', '字')):
        body += '<span data-route="'+str(i)+'">'+lookup_picture('letter' if i == 0 else 'entry', glyph)+'</span>'
    body += '</div></div><p class="lookup-caption">原创演示小字典 · 页码仅供演示</p>'
    for i, entry in enumerate(scene['entries']):
        for j, step in enumerate(entry['steps']):
            body += '<div class="choices" data-dictionary-step data-entry="'+str(i)+'" data-step="'+str(j)+'"'+(' hidden' if i or j else '')+'>'
            for k, option in enumerate(step['options']):
                key = option['assetId']
                body += t.picture_button('lookup-'+str(i)+'-'+str(j)+'-'+str(k), key, assets[key],
                    extra='data-dictionary-choice data-asset="'+escape(key,quote=True)+'"')
            body += '</div>'
    body += '<div class="progress" aria-label="查字进度">'+''.join('<i data-progress="'+str(i)+'"></i>' for i in range(len(scene['entries'])))+'</div><div class="tools">'
    for identity,label,icon,extra in [('start','听老师带着查','start','data-cancel'),('replay','再听提示','replay','data-cancel'),('reset','重新查找','reset','data-cancel'),('next','下一步','next','')]:
        body += t.button(identity,label,icon,extra)
    body += '</div><style>.lookup-header{display:flex;align-items:center;justify-content:center;gap:16px}.lookup-source{width:min(48%,310px)}.lookup-source svg{width:100%;height:150px}.lookup-route{display:flex;gap:8px}.lookup-route span{width:60px;border-bottom:4px solid #c6d4bd}.lookup-route svg{width:100%;height:65px}.lookup-route .done{border-color:#6a967d}.lookup-caption{text-align:center;margin:2px 0 6px;color:#60745f;font-size:14px}.choices{max-width:620px;gap:12px}.choices button{min-height:110px}.choices svg{max-height:130px}[hidden]{display:none!important}@media(max-width:520px){.lookup-header{gap:5px}.lookup-route{gap:3px}.lookup-route span{width:42px}.lookup-source svg{height:125px}.choices{gap:6px}.choices button{padding:3px;min-height:90px}.choices svg{max-height:108px}}</style>'
    config = {'entries':scene['entries'],'intro':scene['initialCueId'],'retry':scene['retryCueId'],'complete':scene['completeCueId']}
    return t.scene_html(scene, body, LOOKUP.replace('CONFIG',t.js(config)))

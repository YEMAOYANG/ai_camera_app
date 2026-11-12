"""Connect a finished game observation to the classroom checkpoint channel."""

from copy import deepcopy
import json

from backend.content.courseware_observation import CARD_ID, VIEWS, validate_card


_CHECKPOINT = """<script>
(() => {
  let lastObservation = null;
  window.miraActivityCheckpoint = {
    version: 1,
    capture: () => lastObservation,
    restore: (saved) => {
      if (saved?.schemaVersion !== 'mira.game.observation.v1' ||
          saved.kind !== 'simulation' || saved.sceneId !== SCENE_ID) return false;
      lastObservation = saved;
      return true;
    },
  };
  window.addEventListener('mira-game-observation-ready', () => {
    const record = window.K?.game?.observation?.();
    if (record?.sceneId !== SCENE_ID || record.kind !== 'simulation') return;
    lastObservation = record;
    window.dispatchEvent(new Event('mira-activity-state-changed'));
  });
})();
</script>"""


def embed(html, card, *, scene_id, image_urls):
    if CARD_ID in html or 'miraActivityCheckpoint =' in html:
        raise ValueError('observation card already has a checkpoint')
    resolved = deepcopy(validate_card(card, is_image=image_urls.__contains__))
    for level in resolved['levels']:
        for trial in level['trials']:
            for view in VIEWS:
                trial[view] = {ident: {**outcome, 'image': image_urls[outcome['image']]}
                               for ident, outcome in trial[view].items()}
    validate_card(resolved)
    payload = json.dumps(resolved, ensure_ascii=False, separators=(',', ':')).replace('<', r'\u003c')
    manifest = f'<script type="application/json" id="{CARD_ID}">{payload}</script>'
    checkpoint = _CHECKPOINT.replace('SCENE_ID', json.dumps(scene_id))
    start, end, suffix = html.rpartition('</body>')
    if not end:
        raise ValueError('observation card requires a classroom document')
    return start + manifest + checkpoint + end + suffix

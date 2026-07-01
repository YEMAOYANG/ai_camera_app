# Vision live regression images

This directory holds **synthetic** fixture images for live Kimi Vision regression.

## Privacy

- Committed images are **synthetic / staged** scenes, not photos of real children.
- Do not replace them with identifiable child photos without review.

## Layout

```text
vision_images/
  posture/
    homework_low_head.jpg
    homework_good_posture.jpg
  meal/
    meal_standing_on_chair.jpg
    meal_distracted_phone.jpg
```

## Run live regression

Requires Moonshot/Kimi credentials (same as backend worker):

```sh
cd backend
export KIMI_VISION_LIVE=1
export AI_PROVIDER=kimi
export AI_API_KEY=...
export AI_BASE_URL=https://api.moonshot.cn/v1
export AI_VISION_MODEL=kimi-k2.5  # or your vision model
export AI_VISION_TIMEOUT_SECONDS=60

python3 -m unittest tests.test_vision_live_regression -v
```

Cases without a local image file are **skipped** (not failed).

Live posture cases allow equivalent risk labels (`low_head`, `leaning_too_close`, etc.) and do not pin exact `raw_activity` wording from Kimi.

## What is asserted

Live tests validate **structured fields** after validator + enrich + payload build:

- `activity`, `raw_activity`, `posture_status`, `meal_standing`, `meal_etiquette_issue`
- `payload.scenario`, `signals[0].signalType`
- `session.bucket`, `session.risk`

Natural-language `description` alone is not sufficient.

Live model wording can vary across runs. The live regression therefore keeps the
business-critical assertions strict, while allowing equivalent posture risk
labels such as `low_head` and `leaning_too_close`, and allowing meal distraction
cases to pass when the structured meal issue and payload are correct even if
the high-level `activity` is generic.

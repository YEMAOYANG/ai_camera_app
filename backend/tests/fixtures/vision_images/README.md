# Vision live regression images

This directory holds **optional** fixture images for live Kimi Vision regression.

## Privacy

- Do **not** commit photos of real children unless they are fully anonymized/synthetic.
- Default repo state: **no images** — only this README and `.gitkeep` placeholders.
- Add local files under `posture/` or `meal/` for manual runs.

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

python3 -m unittest tests.test_vision_live_regression -v
```

Cases without a local image file are **skipped** (not failed).

## What is asserted

Live tests validate **structured fields** after validator + enrich + payload build:

- `activity`, `raw_activity`, `posture_status`, `meal_standing`, `meal_etiquette_issue`
- `payload.scenario`, `signals[0].signalType`
- `session.bucket`, `session.risk`

Natural-language `description` alone is not sufficient.

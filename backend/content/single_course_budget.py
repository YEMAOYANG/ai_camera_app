"""Build a temporary exact-scope operator policy; never enable the default registry."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from content.learning_budget_policy import LearningBudgetPolicy, UNITS, PURPOSES, digest
from services.learning_curriculum_preparation_contract import build_preparation_target, preparation_target_fingerprint


PRICE_SOURCES = {
    "deepseek": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
    "qwen": "https://help.aliyun.com/zh/model-studio/model-pricing",
    "brave": "https://brave.com/search/api/",
    "baidu": "https://cloud.baidu.com/doc/qianfan/s/1mh4sv6c4",
}


def validate_single_search_provider(policy, readiness, *, frozen_prices=None):
    """Check the complete future search dependency before spending on content."""
    if not isinstance(readiness, dict) or readiness.get('ready') is not True:
        raise ValueError('formal runtime/search configuration is not ready; no production call allowed')
    search = readiness.get('webSearch')
    if not isinstance(search, dict):
        raise ValueError('formal runtime did not report its search provider')
    provider = search.get('providerId')
    models = {'brave': 'brave-search', 'baidu': 'baidu-web-search'}
    if (not isinstance(provider, str) or provider not in models
            or search.get('productionMode') != provider + '_api'
            or search.get('formalProductionConfigured') is not True
            or search.get('verification') != 'configuration_only'):
        raise ValueError('formal search API configuration is invalid')
    template = policy.raw['authorizationTemplates']['production']
    keys = template['priceKeys'] if template else []
    profiles = [(key, policy.price(key)) for key in keys
                if 'search_requests' in policy.price(key)['allowedUnits']]
    if (len(profiles) != 1 or profiles[0][1]['provider'] != provider
            or profiles[0][1]['model'] != models[provider]):
        raise ValueError('runtime search provider differs from the selected production budget; no production call allowed')
    key, profile = profiles[0]
    if frozen_prices is not None and (not isinstance(frozen_prices, dict)
                                     or frozen_prices.get(key) != profile):
        raise ValueError('runtime search price is absent or different in the original frozen authorization; no production call allowed')
    return provider


def single_slot_identity(grade, subject, skill, ordinal):
    target = build_preparation_target(grade)
    slots = [s for s in target["courseTargets"] if s["subject"] == subject and s["skillId"] == skill
             and type(ordinal) is int and s["variantOrdinal"] == ordinal]
    if len(slots) != 1:
        raise ValueError("requested slot is not in the frozen curriculum")
    slot = slots[0]
    fingerprint = preparation_target_fingerprint(target)
    request = "grade-build:" + fingerprint
    build_id = "catalog_build_" + hashlib.sha256(request.encode()).hexdigest()[:24]
    item_id = "catalog_build_item_" + hashlib.sha256(
        f"{build_id}:{grade}:{subject}:{skill}:{ordinal}".encode()).hexdigest()[:24]
    scope = {"purpose": "production", "gradeCode": grade, "subject": subject,
             "courseId": "catalog-item:" + item_id,
             "courseVersion": digest({"curriculumVersion": target["curriculumVersion"],
                                     "boundaryVersion": slot["boundaryVersion"], "targetSpec": target}),
             "productionJobId": item_id, "userId": None, "sessionId": None,
             "approvalReference": request}
    return {"targetFingerprint": fingerprint, "buildId": build_id, "buildItemId": item_id,
            "scope": scope, "slot": deepcopy(slot)}


def build_single_course_policy(*, grade, subject, skill, ordinal, now, ttl_ms=10800000,
                               money_micros=10000000, vision_provider="deepseek", search_provider="brave"):
    if not 60000 <= ttl_ms <= 6 * 3600000 or not 1 <= money_micros <= 10000000:
        raise ValueError("operator policy exceeds this run's time or CNY10 ceiling")
    if vision_provider not in {"openai", "deepseek"}:
        raise ValueError("unreviewed visual provider")
    if search_provider not in {"brave", "baidu"}:
        raise ValueError("unreviewed search provider")
    identity = single_slot_identity(grade, subject, skill, ordinal)
    raw = LearningBudgetPolicy.load().raw
    raw.update(enabled=True, version=f"single-course-2026-09-10:{identity['buildItemId']}")
    maximum = {**dict.fromkeys(UNITS, 0), "calls": 256, "input_tokens": 2000000,
               "output_tokens": 400000, "characters": 60000, "audio_ms": 7200000,
               "search_requests": 20, "images": 2, "money_micros": money_micros}
    zero = dict.fromkeys(UNITS, 0)
    raw["limits"] = {"global": {"day": maximum, "month": maximum, "maxInflightCalls": 4},
        "purposes": {p: {"day": maximum if p == "production" else zero,
                          "month": maximum if p == "production" else zero} for p in PURPOSES},
        "user": {"day": zero, "month": zero}, "course": {"lifetime": maximum}, "authorization": maximum}
    # Admission, not polling, protects the CNY2 needed to actually learn the sample.
    for window in ('day', 'month'):
        raw['limits']['purposes']['production'][window] = {**maximum, 'money_micros': min(money_micros, 8000000)}
    def price(provider, model, maxima, rates, *, version="official-2026-09-10-peak-uncached-ceiling.v1"):
        return {"provider": provider, "model": model, "version": version,
                "allowedUnits": ["calls", *maxima], "perCallMax": {"calls": 1, **maxima},
                "microsPerMillionUnits": {"calls": 0, **rates}}
    # Actual billing may be lower (off-peak, cache, credits). Never anticipate that discount.
    raw["prices"] = {
        "deepseek-pro-peak": price("deepseek", "deepseek-v4-pro", {"input_tokens": 500000, "output_tokens": 65536}, {"input_tokens": 9000000, "output_tokens": 27000000}),
        "deepseek-flash-peak": price("deepseek", "deepseek-v4-flash", {"input_tokens": 500000, "output_tokens": 32768}, {"input_tokens": 3000000, "output_tokens": 9000000}),
        "deepseek-vision-peak": price(vision_provider, "deepseek-v4-flash-vision-exp", {"input_tokens": 65536, "output_tokens": 8192}, {"input_tokens": 3000000, "output_tokens": 9000000}),
        "qwen-tts-beijing": price("qwen-tts", "qwen3-tts-flash", {"characters": 10000}, {"characters": 80000000}),
        "qwen-asr-beijing": price("qwen-asr", "qwen3-asr-flash", {"audio_ms": 600000}, {"audio_ms": 220000}),
        "qwen-image-beijing": price("qwen-image", "qwen-image-max", {"images": 1}, {"images": 500000000000}),
    }
    if search_provider == "brave":
        # Search $5/1000; budget conversion 8 CNY/USD is an explicit ceiling, not live FX.
        raw["prices"]["brave-search-ceiling"] = price("brave", "brave-search",
            {"search_requests": 1}, {"search_requests": 40000000000})
    else:
        # Official standard edition is CNY0.036/request; Native freezes edition=standard.
        # Exclude turbo (CNY0.072) and do not treat daily free credits as a zero price.
        raw["prices"]["baidu-search-standard-2026-09-10"] = price("baidu", "baidu-web-search",
            {"search_requests": 1}, {"search_requests": 36000000000},
            version="official-2026-09-10-baidu-standard.v1")
    raw["authorizationTemplates"] = {p: None for p in PURPOSES}
    raw["authorizationTemplates"]["production"] = {"maxUnits": maximum, "priceKeys": list(raw["prices"]), "ttlMs": ttl_ms}
    raw["authorizationWindow"] = {"startsAt": now, "expiresAt": now + ttl_ms, "scopes": [identity["scope"]]}
    return LearningBudgetPolicy(raw), identity


def with_single_teaching_scope(policy, *, identity, scope, now):
    """Append one server-derived student/session; keep the original time and total cap."""
    raw = deepcopy(policy.raw)
    window = raw.get('authorizationWindow') or {}
    if (not raw['enabled'] or not window.get('startsAt', now + 1) <= now < window.get('expiresAt', 0)
            or window.get('scopes') not in ([identity['scope']], [identity['scope'], scope])):
        raise ValueError('teaching authorization requires this exact active single-slot policy')
    if (scope.get('purpose') != 'required_teaching' or scope.get('gradeCode') != identity['scope']['gradeCode']
            or scope.get('subject') != identity['scope']['subject'] or scope.get('productionJobId') is not None
            or not scope.get('userId') or not scope.get('sessionId')):
        raise ValueError('teaching scope must come from the exact published course and student session')
    for window_name in ('day', 'month'):
        if policy.aggregate_limits_enabled and raw['limits']['global'][window_name]['money_micros'] > 10000000:
            raise ValueError('global sample ceiling changed')
    maximum = {**dict.fromkeys(UNITS, 0), 'calls': 96, 'input_tokens': 1000000,
               'output_tokens': 100000, 'characters': 30000, 'audio_ms': 1800000,
               'money_micros': 2000000}
    raw['limits']['purposes']['required_teaching'] = {'day': maximum, 'month': maximum}
    raw['limits']['user'] = {'day': maximum, 'month': maximum}
    raw['authorizationTemplates']['required_teaching'] = {'maxUnits': maximum,
        'priceKeys': ['deepseek-pro-peak', 'deepseek-flash-peak', 'qwen-tts-beijing', 'qwen-asr-beijing'],
        'ttlMs': raw['authorizationTemplates']['production']['ttlMs']}
    raw['authorizationWindow']['scopes'] = [identity['scope'], scope]
    return LearningBudgetPolicy(raw)


def observe_single_course_budget(policy, *, identity):
    """Remove cumulative quotas from one paused sample without changing its grant."""
    raw = deepcopy(policy.raw)
    scopes = (raw.get('authorizationWindow') or {}).get('scopes') or []
    if (raw['enabled'] or not scopes or scopes[0] != identity['scope'] or len(scopes) > 2
            or any(scope['purpose'] != 'required_teaching'
                   or scope['gradeCode'] != identity['scope']['gradeCode']
                   or scope['subject'] != identity['scope']['subject'] for scope in scopes[1:])):
        raise ValueError('metering-only mode requires the original paused single-course policy')
    raw['aggregateLimitsEnabled'] = False
    return LearningBudgetPolicy(raw)

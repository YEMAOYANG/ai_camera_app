import unittest

from content.learning_budget_policy import LearningBudgetPolicy, digest
from content.single_course_budget import build_single_course_policy, with_single_teaching_scope, validate_single_search_provider, observe_single_course_budget


class SingleCourseBudgetTest(unittest.TestCase):
    def test_observe_changes_only_explicit_switch_on_original_paused_sample(self):
        policy, identity = build_single_course_policy(grade='primary_6', subject='math',
            skill='fraction_ratio_percentage', ordinal=1, now=1000)
        self.assertTrue(policy.aggregate_limits_enabled)
        self.assertEqual(policy.sha256, digest(policy.raw))
        with self.assertRaisesRegex(ValueError, 'paused single-course'):
            observe_single_course_budget(policy, identity=identity)
        policy.raw['enabled'] = False
        result = observe_single_course_budget(policy, identity=identity)
        self.assertEqual(result.raw, {**policy.raw, 'aggregateLimitsEnabled': False})
        self.assertFalse(result.aggregate_limits_enabled)
        self.assertFalse(result.raw['enabled'])
        with self.assertRaisesRegex(ValueError, 'boolean'):
            LearningBudgetPolicy({**policy.raw, 'aggregateLimitsEnabled': 0})

    def test_runtime_search_matches_policy_and_existing_frozen_price_before_production(self):
        options = dict(grade='primary_6', subject='math', skill='fraction_ratio_percentage', ordinal=1, now=1000)
        brave, _ = build_single_course_policy(**options)
        baidu, _ = build_single_course_policy(**options, search_provider='baidu')
        ready = {'ready': True, 'webSearch': {'providerId': 'baidu', 'productionMode': 'baidu_api',
            'formalProductionConfigured': True, 'verification': 'configuration_only'}}
        self.assertEqual(validate_single_search_provider(baidu, ready), 'baidu')
        with self.assertRaisesRegex(ValueError, 'differs from the selected production budget'):
            validate_single_search_provider(brave, ready)
        with self.assertRaisesRegex(ValueError, 'original frozen authorization'):
            validate_single_search_provider(baidu, ready, frozen_prices=brave.raw['prices'])
        self.assertEqual(validate_single_search_provider(baidu, ready, frozen_prices=baidu.raw['prices']), 'baidu')
        changed = {key: dict(value) for key, value in baidu.raw['prices'].items()}
        changed['baidu-search-standard-2026-09-10']['version'] = 'unreviewed-price'
        with self.assertRaisesRegex(ValueError, 'original frozen authorization'):
            validate_single_search_provider(baidu, ready, frozen_prices=changed)

    def test_search_selection_prices_standard_baidu_without_granting_brave_or_changing_scope(self):
        options = dict(grade='primary_6', subject='math', skill='fraction_ratio_percentage', ordinal=1, now=1000)
        brave, identity = build_single_course_policy(**options)
        baidu, baidu_identity = build_single_course_policy(**options, search_provider='baidu')
        self.assertEqual(baidu_identity, identity)
        self.assertEqual(baidu.raw['authorizationWindow'], brave.raw['authorizationWindow'])
        self.assertEqual(baidu.raw['limits'], brave.raw['limits'])
        self.assertIn('brave-search-ceiling', brave.raw['prices'])
        self.assertNotIn('brave-search-ceiling', baidu.raw['prices'])
        key = 'baidu-search-standard-2026-09-10'
        self.assertNotIn(key, brave.raw['prices'])
        profile = baidu.price(key)
        self.assertEqual((profile['provider'], profile['model']), ('baidu', 'baidu-web-search'))
        self.assertIn(key, baidu.raw['authorizationTemplates']['production']['priceKeys'])
        self.assertEqual(baidu.measure({'calls': 1, 'search_requests': 1}, profile, reservation=True)['money_micros'], 36000)
        with self.assertRaises(ValueError):
            baidu.measure({'calls': 1, 'search_requests': 2}, profile, reservation=True)
        with self.assertRaises(ValueError):
            build_single_course_policy(**options, search_provider='public_html')

    def test_one_teaching_session_preserves_global_total_expiry_and_disabled_optional(self):
        policy, identity = build_single_course_policy(grade='primary_6', subject='math',
            skill='fraction_ratio_percentage', ordinal=1, now=1000)
        scope = {**identity['scope'], 'purpose': 'required_teaching', 'courseId': 'published-course',
            'courseVersion': 'v1', 'userId': 'child', 'sessionId': 'learning-session', 'productionJobId': None}
        result = with_single_teaching_scope(policy, identity=identity, scope=scope, now=2000)
        self.assertEqual(result.raw['limits']['global']['day']['money_micros'], 10000000)
        self.assertEqual(result.raw['limits']['purposes']['production']['day']['money_micros'], 8000000)
        self.assertEqual(result.raw['authorizationTemplates']['required_teaching']['maxUnits']['money_micros'], 2000000)
        self.assertEqual(result.raw['authorizationWindow']['expiresAt'], policy.raw['authorizationWindow']['expiresAt'])
        self.assertEqual(result.raw['authorizationWindow']['scopes'], [identity['scope'], scope])
        self.assertIsNone(result.raw['authorizationTemplates']['optional_interaction'])
        self.assertIsNone(policy.raw['authorizationTemplates']['required_teaching'])
        self.assertEqual(with_single_teaching_scope(result, identity=identity, scope=scope, now=2001).sha256, result.sha256)
        with self.assertRaises(ValueError):
            with_single_teaching_scope(result, identity=identity, scope={**scope, 'sessionId': 'another-session'}, now=2001)
        with self.assertRaises(ValueError):
            with_single_teaching_scope(result, identity=identity, scope=scope, now=result.raw['authorizationWindow']['expiresAt'])

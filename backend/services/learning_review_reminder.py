"""Bounded capability adapter for review reminders, never plain camera speak."""
from core.security import now_ms
from core.errors import ApiError


class SafeReviewReminderSender:
    def __init__(self, runtime_resolver, *, clock=now_ms):
        self.resolver, self.clock = runtime_resolver, clock

    def __call__(self, *, family_id, child_id, task_id, request_id,
                 appointment_revision, expires_at, non_preemptive, text):
        if non_preemptive is not True or self.clock() >= expires_at:
            return {'delivered': False, 'reason': 'expired'}
        try:
            resolved = self.resolver.resolve(family_id=family_id, require_device=True)
        except ApiError:
            return {'delivered': False, 'reason': 'device_unavailable'}
        adapter = resolved.bridge.adapter
        capabilities = getattr(adapter, 'review_reminder_capabilities', None)
        speak = getattr(adapter, 'speak_review_if_idle', None)
        if not callable(capabilities) or not callable(speak):
            return {'delivered': False, 'reason': 'silent_unsupported'}
        supported = capabilities()
        if (not isinstance(supported, dict) or supported.get('schemaVersion') != 1 or
                any(supported.get(k) is not True for k in ('atomicIdleSpeech','expiry','idempotency',
                    'noQueue','appointmentRevision','sleepAndQuietHours'))):
            return {'delivered': False, 'reason': 'silent_unsupported'}
        if self.clock() >= expires_at:
            return {'delivered': False, 'reason': 'expired'}
        result = speak({'requestId': request_id,'appointmentRevision':appointment_revision,
            'expiresAt':expires_at,'text':text,'nonPreemptive':True,'familyId':family_id,
            'childId':child_id,'taskId':task_id,'deviceId':resolved.device_id})
        if (not isinstance(result,dict) or result.get('requestId') != request_id or
                result.get('appointmentRevision') != appointment_revision):
            return {'delivered':False,'reason':'receipt_mismatch'}
        if result.get('delivered') is True:
            played=result.get('playedAt')
            if type(played) is not int or not 0 < played <= min(expires_at,self.clock()):
                return {'delivered':False,'reason':'invalid_delivery_time'}
            return {'delivered':True,'playedAt':played,'requestId':request_id,'appointmentRevision':appointment_revision}
        return {'delivered':False,'reason':str(result.get('reason') or 'not_delivered')[:80]}

"""Optional document-specific adapter protocol. Legacy snapshot is NOT a fallback.

Existing camera adapters deliberately do not implement this protocol. A device
must have an operator-reviewed validation evidence id and an atomic read-only
capture method before it can be used for homework.
"""
from dataclasses import dataclass
import hashlib
from typing import Protocol
from core.errors import ApiError


@dataclass(frozen=True)
class DocumentCaptureCapability:
    device_id: str
    validation_evidence_id: str
    current_view_only: bool
    non_interrupting: bool
    full_resolution: bool
    shared_configuration_unchanged: bool


@dataclass(frozen=True)
class DocumentCaptureRequest:
    request_id: str
    device_id: str
    child_id: str
    task_id: str
    expires_at: int


@dataclass(frozen=True)
class DocumentCaptureReceipt:
    request_id: str
    device_id: str
    captured_at: int
    body: bytes
    content_type: str
    sha256: str
    orientation: int = 0


class DocumentCaptureAdapter(Protocol):
    def document_capture_capability(self) -> DocumentCaptureCapability:
        """Read a static capability declaration; no config recovery or device mutation."""
        ...

    def capture_document_if_idle(self, request: DocumentCaptureRequest) -> DocumentCaptureReceipt:
        """Atomically refuse if busy; capture once from current view, no PTZ/restart.

        Must not pause/stop care, media, speech, reminders, or change shared
        resolution/focus/exposure. Honour expiry and deduplicate request_id.
        """
        ...


def require_document_capture(adapter, device_id, approved_evidence_ids):
    capability_fn=getattr(adapter,'document_capture_capability',None)
    capture=getattr(adapter,'capture_document_if_idle',None)
    if not callable(capability_fn) or not callable(capture):
        raise ApiError('homework_document_capture_unavailable','这台设备尚未通过作业拍摄验收，请使用家长App拍照',409)
    capability=capability_fn()
    if (not isinstance(capability,DocumentCaptureCapability) or capability.device_id!=device_id
        or capability.validation_evidence_id not in approved_evidence_ids
        or not all(value is True for value in (capability.current_view_only,capability.non_interrupting,
                    capability.full_resolution,capability.shared_configuration_unchanged))):
        raise ApiError('homework_document_capture_unavailable','这台设备尚未通过作业拍摄验收，请使用家长App拍照',409)
    return capture


def validate_document_receipt(receipt,request,now):
    if (not isinstance(receipt,DocumentCaptureReceipt) or receipt.request_id!=request.request_id
        or receipt.device_id!=request.device_id or not now-60000<=receipt.captured_at<=now+5000
        or now>request.expires_at or receipt.orientation not in {0,90,180,270}
        or receipt.content_type not in {'image/jpeg','image/png'}
        or hashlib.sha256(receipt.body).hexdigest()!=receipt.sha256):
        raise ApiError('homework_capture_receipt_invalid','拍摄回执未通过校验，请使用App补拍',409)
    return receipt

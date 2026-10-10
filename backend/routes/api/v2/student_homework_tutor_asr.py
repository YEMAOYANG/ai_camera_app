"""Bounded, child-scoped microphone transcription for one homework question."""
from flask import Blueprint, jsonify, request
from core.errors import ApiError
from routes.api.v1.homework import endpoint, service
from schemas.auth import bearer_token
from services.homework_tutor_asr_service import HomeworkTutorAsrService, MAX_AUDIO_BYTES

student_homework_tutor_asr_bp = Blueprint('student_homework_tutor_asr_v2', __name__)


def item_revision(value):
    try:
        if not isinstance(value, str) or not value.isascii() or not value.isdigit():
            raise ValueError()
        result = int(value)
        if result < 1:
            raise ValueError()
        return result
    except ValueError:
        raise ApiError('homework_revision_conflict', '请携带题目版本', 400)


@student_homework_tutor_asr_bp.route('/homework/<identity>/items/<item_id>/tutor/transcribe', methods=['POST', 'GET'])
@endpoint
def transcribe(identity, item_id):
    svc = HomeworkTutorAsrService(service())
    token = bearer_token(request)
    if request.method == 'GET':
        if set(request.args) != {'itemRevision', 'idempotencyKey'} or any(len(request.args.getlist(key)) != 1 for key in request.args):
            raise ApiError('homework_asr_request_invalid', '语音查询参数无效', 400)
        return jsonify(svc.get(token, identity, item_id,
            item_revision=item_revision(request.args.get('itemRevision')),
            idempotency_key=request.args.get('idempotencyKey')))
    if request.content_length is not None and request.content_length > MAX_AUDIO_BYTES + 65536:
        raise ApiError('homework_asr_audio_size', '请录制不超过60秒的语音', 413)
    if (set(request.form) != {'itemRevision', 'idempotencyKey'} or set(request.files) != {'audio'}
            or any(len(request.form.getlist(key)) != 1 for key in request.form)
            or len(request.files.getlist('audio')) != 1):
        raise ApiError('homework_asr_request_invalid', '语音提问参数无效', 400)
    return jsonify(svc.transcribe(token, identity, item_id,
        {'itemRevision': item_revision(request.form.get('itemRevision')),
         'idempotencyKey': request.form.get('idempotencyKey')}, request.files['audio'].read(MAX_AUDIO_BYTES + 1)))


@student_homework_tutor_asr_bp.get('/homework/<identity>/items/<item_id>/tutor/transcribe/<transcription_id>')
@endpoint
def receipt(identity, item_id, transcription_id):
    if request.args:
        raise ApiError('homework_asr_request_invalid', '语音查询参数无效', 400)
    return jsonify(HomeworkTutorAsrService(service()).get(bearer_token(request), identity, item_id,
        transcription_id=transcription_id))

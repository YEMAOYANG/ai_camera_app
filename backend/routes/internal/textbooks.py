from flask import Blueprint, jsonify, request, send_file

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.service_factory import internal_request_guard, textbook_learning_service, textbook_classroom_service
from content.textbook_journey import VerifiedActivityAudio

internal_textbooks_bp = Blueprint("internal_textbooks", __name__)


def authorize():
    internal_request_guard().authorize(route=request.path, headers=request.headers, source_ip=request.remote_addr)


@internal_textbooks_bp.post('/runtime/exchange')
def exchange():
    try:
        authorize()
        return jsonify(textbook_classroom_service().exchange(json_body(request).get('ticket')))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.post('/runtime/validate')
def validate_runtime():
    try:
        authorize()
        return jsonify(textbook_classroom_service().validate(json_body(request).get('runtimeToken')))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.get('/runtime/classroom')
def classroom():
    try:
        authorize()
        return jsonify(textbook_classroom_service().classroom(request.headers.get('X-Mira-Textbook-Token')))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.post('/runtime/paid-call')
def classroom_interaction():
    try:
        authorize()
        return jsonify(textbook_classroom_service().admit_interaction(
            request.headers.get('X-Mira-Textbook-Token'), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.route('/runtime/events', methods=['GET', 'POST'])
def events():
    try:
        authorize()
        return jsonify(textbook_classroom_service().events(request.headers.get('X-Mira-Textbook-Token'),
            json_body(request) if request.method == 'POST' else None))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.route('/runtime/quiz', methods=['GET', 'POST'])
def quiz():
    try:
        authorize()
        data = json_body(request) if request.method == 'POST' else None
        if data is not None and (set(data) != {'answers'} or not isinstance(data['answers'], dict)):
            raise ApiError('textbook_answers_invalid', '回答格式无效', 400)
        return jsonify(textbook_classroom_service().quiz(request.headers.get('X-Mira-Textbook-Token'),
            data['answers'] if data is not None else None))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.route('/runtime/play', methods=['GET', 'POST'])
def play():
    try:
        authorize()
        return jsonify(textbook_classroom_service().play(request.headers.get('X-Mira-Textbook-Token'),
            json_body(request) if request.method == 'POST' else None))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.post("/import")
def import_manifest():
    try:
        authorize()
        return jsonify(textbook_learning_service().import_manifest(json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.post("/prepare")
def prepare():
    try:
        authorize()
        return jsonify(textbook_learning_service().prepare(json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.post("/bind-published")
def bind_published():
    try:
        authorize()
        return jsonify(textbook_learning_service().bind_published(json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.get('/runtime/play-audio/<asset>')
def play_audio(asset):
    try:
        authorize()
        path = textbook_classroom_service().activity_audio(request.headers.get('X-Mira-Textbook-Token'), asset)
        response = send_file(path, mimetype='audio/wav', conditional=True,
            **({'download_name': path.name, 'etag': path.sha256} if isinstance(path, VerifiedActivityAudio) else {}))
        response.headers['Cache-Control'] = 'private, no-store'
        return response
    except ApiError as exc:
        return error_response(exc)

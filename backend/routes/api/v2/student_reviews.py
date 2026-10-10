from flask import Blueprint, current_app, jsonify, request, send_file
from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body

student_reviews_bp = Blueprint('student_reviews', __name__)


def service():
    from services.service_factory import learning_review_service
    if not current_app.config.get('LEARNING_REVIEW_ENABLED',False):
        raise ApiError('learning_reviews_disabled','学习复习功能尚未启用',503)
    return learning_review_service()


def call(fn):
    try:return jsonify(fn())
    except ApiError as exc:return error_response(exc)


@student_reviews_bp.get('')
def reviews():
    if not current_app.config.get('LEARNING_REVIEW_ENABLED',False):
        # Authenticate even a disabled read; no student identity is inferred.
        from services.service_factory import student_auth_service
        try:student_auth_service().authenticate(bearer_token(request))
        except ApiError as exc:return error_response(exc)
        return jsonify({'ok':True,'enabled':False,'schemaVersion':'mira.learning.reviews.v1','reviews':[]})
    return call(lambda:service().student_list(bearer_token(request)))


@student_reviews_bp.get('/<run_id>')
def detail(run_id):
    return call(lambda:service().student_detail(bearer_token(request),run_id))


@student_reviews_bp.post('/<run_id>/actions')
def action(run_id):
    return call(lambda:service().student_action(bearer_token(request),run_id,json_body(request)))


@student_reviews_bp.post('/<run_id>/answers')
def answer(run_id):
    return call(lambda:service().answer(bearer_token(request),run_id,json_body(request)))


@student_reviews_bp.get('/<run_id>/media/<asset>')
def audio(run_id,asset):
    try:
        path=service().audio(bearer_token(request),run_id,asset)
        result=send_file(path,mimetype='audio/mpeg' if str(path).lower().endswith('.mp3') else 'audio/wav',conditional=True)
        result.headers['Cache-Control']='private, no-store'
        return result
    except ApiError as exc:return error_response(exc)

from flask import Blueprint, current_app, jsonify, request
from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body

parent_review_preferences_bp = Blueprint('parent_review_preferences', __name__)
parent_learning_reviews_bp = Blueprint('parent_learning_reviews', __name__)
parent_learning_weaknesses_bp = Blueprint('parent_learning_weaknesses', __name__)


def service():
    from services.service_factory import learning_review_service
    if not current_app.config.get('LEARNING_REVIEW_ENABLED', False):
        raise ApiError('learning_reviews_disabled', '学习复习功能尚未启用', 503)
    return learning_review_service()


def call(fn):
    try:
        return jsonify(fn())
    except ApiError as exc:
        return error_response(exc)


@parent_review_preferences_bp.route('/<child_id>/review-preferences', methods=['GET','PUT'])
def preferences(child_id):
    return call(lambda: service().preferences(bearer_token(request), child_id, json_body(request) if request.method=='PUT' else None))


@parent_learning_reviews_bp.get('')
def reviews():
    return call(lambda: service().parent_list(bearer_token(request), request.args.get('childId')))


@parent_learning_reviews_bp.get('/<run_id>')
def detail(run_id):
    return call(lambda: service().parent_detail(bearer_token(request),request.args.get('childId'),run_id))


@parent_learning_reviews_bp.post('/<run_id>/schedule-actions')
def schedule(run_id):
    return call(lambda: service().schedule_action(bearer_token(request),run_id,json_body(request)))


@parent_learning_weaknesses_bp.get('/weaknesses')
def weaknesses():
    return call(lambda: service().parent_weaknesses(bearer_token(request),request.args.get('childId')))

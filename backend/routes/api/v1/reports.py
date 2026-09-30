from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import profile_service


reports_bp = Blueprint("reports", __name__)
growth_bp = Blueprint("growth", __name__)


@reports_bp.route('/learning/<session_id>/coaching', methods=['GET', 'PUT'])
def learning_coaching(session_id):
    try:
        if request.method == 'PUT':
            if request.args:
                raise ApiError('coaching_invalid', '辅导记录参数无效', 400)
            result = profile_service().learning_coaching(bearer_token(request), session_id, data=json_body(request))
        else:
            if set(request.args) != {'recordDate'}:
                raise ApiError('coaching_invalid', '请选择学习记录日期', 400)
            result = profile_service().learning_coaching(bearer_token(request), session_id,
                record_date=request.args['recordDate'])
        return jsonify(result)
    except ApiError as exc:
        return error_response(exc)


@reports_bp.get("/daily")
def daily():
    try:
        return jsonify(profile_service().daily_report(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@reports_bp.get("/weekly")
def weekly():
    try:
        return jsonify(profile_service().weekly_report(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@growth_bp.get("/moments")
def moments():
    try:
        return jsonify(profile_service().growth_moments(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)

from __future__ import annotations

from flask import Blueprint, jsonify

from services.service_factory import profile_service


app_info_bp = Blueprint("app_info", __name__)


@app_info_bp.get("/about")
def about():
    return jsonify(profile_service().app_about())

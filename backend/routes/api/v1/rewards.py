from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import reward_service


rewards_bp = Blueprint("rewards", __name__)


@rewards_bp.get("/items")
def list_items():
    try:
        return jsonify(reward_service().list_items(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@rewards_bp.post("/items")
def create_item():
    try:
        return jsonify(reward_service().create_item(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@rewards_bp.get("/items/<item_id>")
def get_item(item_id: str):
    try:
        return jsonify(reward_service().get_item(bearer_token(request), item_id))
    except ApiError as exc:
        return error_response(exc)


@rewards_bp.patch("/items/<item_id>")
def update_item(item_id: str):
    try:
        return jsonify(reward_service().update_item(bearer_token(request), item_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@rewards_bp.get("/redemptions")
def list_redemptions():
    try:
        return jsonify(reward_service().list_redemptions(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@rewards_bp.post("/redemptions")
def create_redemption():
    try:
        return jsonify(reward_service().create_redemption(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@rewards_bp.post("/redemptions/<redemption_id>/fulfill")
def fulfill_redemption(redemption_id: str):
    try:
        return jsonify(reward_service().fulfill_redemption(bearer_token(request), redemption_id))
    except ApiError as exc:
        return error_response(exc)


@rewards_bp.post("/redemptions/<redemption_id>/cancel")
def cancel_redemption(redemption_id: str):
    try:
        return jsonify(reward_service().cancel_redemption(bearer_token(request), redemption_id))
    except ApiError as exc:
        return error_response(exc)

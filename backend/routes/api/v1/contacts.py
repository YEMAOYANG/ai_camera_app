from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import profile_service


contacts_bp = Blueprint("contacts", __name__)


@contacts_bp.get("/emergency")
def list_contacts():
    try:
        return jsonify(profile_service().list_contacts(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@contacts_bp.post("/emergency")
def create_contact():
    try:
        return jsonify(profile_service().create_contact(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@contacts_bp.patch("/emergency/<contact_id>")
def update_contact(contact_id: str):
    try:
        return jsonify(profile_service().update_contact(bearer_token(request), contact_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@contacts_bp.delete("/emergency/<contact_id>")
def delete_contact(contact_id: str):
    try:
        return jsonify(profile_service().delete_contact(bearer_token(request), contact_id))
    except ApiError as exc:
        return error_response(exc)

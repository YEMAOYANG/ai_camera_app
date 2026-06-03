from __future__ import annotations

from flask import jsonify


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AuthError(ApiError):
    pass


def error_response(exc: ApiError):
    return jsonify({"ok": False, "error": exc.code, "message": exc.message}), exc.status_code

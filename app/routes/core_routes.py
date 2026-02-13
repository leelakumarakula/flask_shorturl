from flask import Blueprint
from ..utils.response import api_response

core_bp = Blueprint("core", __name__)


@core_bp.route("/")
def root():
    return api_response(True, "Use Angular frontend for UI.", None)



@core_bp.route("/health")
def health():
    return {"status": "ok"}, 200

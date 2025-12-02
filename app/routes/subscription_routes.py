from flask import Blueprint, request
from ..extensions import db
from ..utils.response import api_response
from ..routes.auth_routes import token_required
import datetime
from ..utils import plan_limits
subscription_bp = Blueprint("subscription", __name__)

# OPTIONAL – If you have PLAN_LIMITS imported, remove this block
# PLAN_LIMITS = {
#     "pro": {
#         "short_limit": 200,
#         "qr_limit": 150,
#         "custom_limit": 100,
#         "analytics_limit": 1500
#     },
#     "premium": {
#         "short_limit": 1000,
#         "qr_limit": 750,
#         "custom_limit": 500,
#         "analytics_limit": 10000
#     }
# }

@subscription_bp.route("/activate", methods=["POST"])
@token_required
def activate_plan(current_user):
    data = request.get_json() or {}
    plan = data.get("plan")

    if plan not in plan_limits.PLAN_LIMITS:
        return api_response(False, "Invalid plan selected.", None)

    # 30 days validity
    expiry = datetime.datetime.utcnow() + datetime.timedelta(days=30)

    current_user.plan = plan
    current_user.plan_expires = expiry  # ✅ CORRECT FIELD NAME

    db.session.commit()

    return api_response(True, f"{plan.capitalize()} plan activated successfully!", {
        "plan": plan,
        "expires_on": expiry.isoformat()
    })
@subscription_bp.route("/status", methods=["GET"])
@token_required
def subscription_status(current_user):

    return api_response(True, "Subscription status fetched", {
        "plan": current_user.plan,
        "expires_on": current_user.plan_expires.isoformat() if current_user.plan_expires else None,
        "is_active": bool(current_user.plan != "free" and current_user.plan_expires and current_user.plan_expires > datetime.datetime.utcnow())
    })


@subscription_bp.route("/cancel", methods=["POST"])
@token_required
def cancel_subscription(current_user):

    current_user.plan = "free"
    current_user.plan_expires = None

    db.session.commit()

    return api_response(True, "Subscription cancelled. You are now on Free Plan.", {
        "plan": "free",
        "expires_on": None
    })

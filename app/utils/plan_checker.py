# # utils/plan_checker.py
# import datetime
# from ..models.url import Urls
# from ..models.url_analytics import UrlAnalytics
# from .plan_limits import PLAN_LIMITS
# from ..extensions import db


# def _get_limits_for_user(user):
#     return PLAN_LIMITS.get(getattr(user, "plan", "free"), PLAN_LIMITS["free"])


# def check_plan_limits(
#     user,
#     will_create_short=False,
#     will_create_qr=False,
#     will_create_custom=False
# ):
#     """
#     Plan check for links, QR codes, and custom short URLs.
#     SQL Server safe (uses == True/False instead of IS).
#     """
#     limits = _get_limits_for_user(user)

#     # ---- SHORT LINKS COUNT ---- (count only show_short=True)
#     # short_count = Urls.query.filter(
#     #     Urls.user_id == user.id,
#     #     Urls.show_short == True
#     # ).count()

#     # if will_create_short and short_count >= limits["links"]:
#     #     return False, f"You reached your short link limit ({limits['links']})."

#     if will_create_short and user.total_links_created >= limits["links"]:
#         return False, f"You have already created {limits['links']} links on the Free plan."


#     # ---- QR COUNT ---- (count only QR generated)
#     qr_count = Urls.query.filter(
#         Urls.user_id == user.id,
#         Urls.qr_generated == True
#     ).count()

#     if will_create_qr and qr_count >= limits["qrs"]:
#         return False, f"You reached your QR limit ({limits['qrs']})."

#     # ---- CUSTOM COUNT ---- (true user-typed custom short codes)
#     custom_count = Urls.query.filter(
#         Urls.user_id == user.id,
#         Urls.custom == True
#     ).count()

#     if will_create_custom and custom_count >= limits["custom"]:
#         return False, f"You reached your custom short code limit ({limits['custom']})."

#     return True, None


# # ------------------------------------------------
# # 🔥 PER-LINK ANALYTICS LIMIT (7 hits per link)
# # ------------------------------------------------
# def link_analytics_allowed(url_id, user):
#     """
#     Free plan = unlimited analytics per link (no 7-hit limit)
#     Paid plans still use analytics_limit from PLAN_LIMITS.
#     """
#     plan = getattr(user, "plan", "free")

#     # Free plan → unlimited
#     if plan == "free":
#         return True

#     # Paid plans → enforce plan limit
#     limits = _get_limits_for_user(user)
#     max_hits = limits.get("analytics_limit", None)

#     if not max_hits:
#         return True

#     count = UrlAnalytics.query.filter_by(url_id=url_id).count()
#     return count < max_hits

# def can_edit_short_link(user):
#     limits = _get_limits_for_user(user)
#     max_edits = limits.get("edit_limit", 0)

#     if max_edits == 0:
#         return False, "Your plan does not allow editing short URLs."

#     if user.edit_count >= max_edits:
#         return False, f"You reached your edit limit ({max_edits})."

#     return True, None


# # ------------------------------------------------
# # OPTIONAL — still keep your per-plan cleanup
# # ------------------------------------------------
# def enforce_analytics_limits(user):
#     limits = _get_limits_for_user(user)
#     max_records = limits["analytics_limit"]
#     days = limits["analytics_days"]

#     q = UrlAnalytics.query.join(Urls).filter(Urls.user_id == user.id)

#     # Age cleanup
#     if days:
#         cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
#         try:
#             UrlAnalytics.query.join(Urls).filter(
#                 Urls.user_id == user.id,
#                 UrlAnalytics.timestamp < cutoff
#             ).delete(synchronize_session=False)
#             db.session.commit()
#         except:
#             db.session.rollback()

#     # Max count cleanup
#     try:
#         total = q.count()
#         if max_records and total > max_records:
#             excess = total - max_records
#             oldest = q.order_by(UrlAnalytics.timestamp.asc()).limit(excess)
#             for item in oldest:
#                 db.session.delete(item)
#             db.session.commit()
#     except:
#         db.session.rollback()


# utils/plan_checker.py
import datetime
from ..models.url import Urls
from ..models.url_analytics import UrlAnalytics
from .plan_limits import PLAN_LIMITS
from ..extensions import db


def _get_limits_for_user(user):
    return PLAN_LIMITS.get(getattr(user, "plan", "free"), PLAN_LIMITS["free"])


def check_plan_limits(
    user,
    will_create_short=False,
    will_create_qr=False,
    will_create_custom=False
):
    """
    Bitly-style PERMANENT LIMIT CHECKS.
    DELETE does NOT restore usage.
    """

    limits = _get_limits_for_user(user)

    # ---------------------------------------------------
    # 1️⃣ SHORT LINK LIMIT — permanent, never decreases
    # ---------------------------------------------------
    if will_create_short and user.total_links_created >= limits["links"]:
        return False, f"You reached your short link limit ({limits['links']})."

    # ---------------------------------------------------
    # 2️⃣ QR LIMIT — permanent, never decreases
    # ---------------------------------------------------
    if will_create_qr and user.total_qr_created >= limits["qrs"]:
        return False, f"You reached your QR code limit ({limits['qrs']})."

    # ---------------------------------------------------
    # 3️⃣ CUSTOM SHORT CODE LIMIT — permanent, never decreases
    # ---------------------------------------------------
    if will_create_custom and user.total_custom_created >= limits["custom"]:
        return False, f"You reached your custom short code limit ({limits['custom']})."

    return True, None


# ------------------------------------------------
# 🔥 PER-LINK ANALYTICS LIMIT
# ------------------------------------------------
def link_analytics_allowed(url_id, user):
    """
    Free plan → unlimited analytics
    Paid plans → enforce per-URL hit limit
    """
    plan = getattr(user, "plan", "free")

    # Free plan => unlimited analytics
    if plan == "free":
        return True

    limits = _get_limits_for_user(user)
    max_hits = limits.get("analytics_limit", None)

    if not max_hits:
        return True

    count = UrlAnalytics.query.filter_by(url_id=url_id).count()
    return count < max_hits


def can_edit_short_link(user):
    """Check per-plan edit limit."""
    limits = _get_limits_for_user(user)
    max_edits = limits.get("edit_limit", 0)

    if max_edits == 0:
        return False, "Your plan does not allow editing short URLs."

    if user.edit_count >= max_edits:
        return False, f"You reached your edit limit ({max_edits})."

    return True, None


# ------------------------------------------------
# OPTIONAL CLEANUP (DO NOT CHANGE)
# ------------------------------------------------
def enforce_analytics_limits(user):
    limits = _get_limits_for_user(user)
    max_records = limits["analytics_limit"]
    days = limits["analytics_days"]

    q = UrlAnalytics.query.join(Urls).filter(Urls.user_id == user.id)

    # Cleanup by age
    if days:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        try:
            UrlAnalytics.query.join(Urls).filter(
                Urls.user_id == user.id,
                UrlAnalytics.timestamp < cutoff
            ).delete(synchronize_session=False)
            db.session.commit()
        except:
            db.session.rollback()

    # Cleanup by count
    try:
        total = q.count()
        if max_records and total > max_records:
            excess = total - max_records
            oldest = q.order_by(UrlAnalytics.timestamp.asc()).limit(excess)
            for item in oldest:
                db.session.delete(item)
            db.session.commit()
    except:
        db.session.rollback()

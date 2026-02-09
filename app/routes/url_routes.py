import os
import random
import string
import uuid
import datetime
from urllib.parse import urlparse
 
from flask import Blueprint, logging, request, redirect
import json
import requests
from user_agents import parse
# from app.extensions import db, redis_client
from .. import extensions    
 
from ..extensions import db, redis_client
from flask import current_app
from ..models.url import Urls
from ..models.url_analytics import UrlAnalytics
from ..routes.auth_routes import token_required
from ..utils.response import api_response
from sqlalchemy import cast, Date, func
from werkzeug.security import generate_password_hash, check_password_hash
from ..models.user import User
from ..utils.passwords import verify_and_upgrade_password
from ..utils.static_urls import build_static_url
from ..utils.qr_generator import generate_styled_qr
 
 
url_bp = Blueprint("url", __name__)
 
def get_location_from_ip(ip: str | None) -> dict:
    ip = ip or ""
    try:
        resp = requests.get(f"https://ipwho.is/{ip}", timeout=3)
        data = resp.json()
        if data.get("success"):
            return {
                "country": data.get("country", "Unknown"),
 
                "region": data.get("region", "Unknown"),
 
                "city": data.get("city", "Unknown"),
            }
    except Exception:
        pass
 
    return {"country": "Unknown", "region": "Unknown", "city": "Unknown"}
 
def _shorten_url() -> str:
    chars = string.ascii_letters + string.digits
    while True:
        rand_chars = ''.join(random.choices(chars, k=7))
        short_url = Urls.query.filter_by(short=rand_chars).first()
        if not short_url:
            return rand_chars
 
 
 
 
 
def absolute_qr_path(rel_path: str) -> str:
    """
    Convert a stored relative QR path (e.g. 'qrcodes/qr_123.png')
    into an absolute filesystem path.
    """
    if not rel_path:
        return None
 
    base_static = current_app.static_folder or "static"
    return os.path.join(base_static, rel_path.lstrip("/"))
 
 
@url_bp.route('/create', methods=['POST'])
@token_required
def create(current_user):
    data = request.get_json() or {}
 
    long_url = (data.get("long_url") or "").strip()
    custom_short = (data.get("custom") or "").strip()
    generate_qr = bool(data.get("generate_qr", False))
    title = (data.get("title") or "").strip()
 
    if not long_url:
        return api_response(False, "long_url is required", None)
 
    parsed = urlparse(long_url)
    if not parsed.scheme:
        long_url = "https://" + long_url
 
    # -----------------------------
    # SUBSCRIPTION LIMIT CHECKS (CONSUMPTION BASED)
    # -----------------------------
    plan = current_user.plan
 
    if plan:
        # 1. Consumption Limit: Usage Links
        # Always check link limit because a link is ALWAYS created
        limit_links = current_user.get_limit('max_links')
        if limit_links != -1 and current_user.usage_links >= limit_links:
              return api_response(False, f"Link creation limit reached ({limit_links}). Upgrade to get more.", None)
 
        # 2. Custom Slug Limit
        if custom_short:
            current_custom_count = Urls.query.filter_by(user_id=current_user.id, is_custom=True).count()
            limit_custom = current_user.get_limit('max_custom_links')
            if current_custom_count >= limit_custom:
                return api_response(False, f"Custom link limit reached ({limit_custom}). Please upgrade.", None)
 
        # 3. Consumption Limit: Usage QRs
        if generate_qr:
            limit_qrs = current_user.get_limit('max_qrs')
            if limit_qrs != -1 and current_user.usage_qrs >= limit_qrs:
                return api_response(False, f"QR code limit reached ({limit_qrs}). Please upgrade.", None)
 
    # Short code logic
    is_custom_flag = False
    if custom_short:
        if not custom_short.isalnum():
            return api_response(False, "Custom short URL must be alphanumeric.", None)
        if Urls.query.filter_by(short=custom_short).first():
            return api_response(False, "This custom short URL already exists.", None)
        short_code = custom_short
        is_custom_flag = True
    else:
        short_code = _shorten_url()
 
    base_url = current_app.config.get("BASE_URL")
    short_full = f"{base_url}/{short_code}"
 
    # Optional QR code generation
    qr_path = None
    if generate_qr:
        # Defaults for 'create' endpoint
        c_logo_data = None
        c_logo_path = None
       
        # Enforce default logo for Free plan
        if plan and not current_user.get_limit('allow_qr_styling'):
             default_logo = os.path.join(current_app.static_folder or "static", "image.png")
             if os.path.exists(default_logo):
                  c_logo_path = default_logo
       
       
        qr_path = generate_styled_qr(short_code, color_dark="#000000", style="square", logo_data=c_logo_data, logo_path=c_logo_path)
 
        # -----------------------------
        # LOGO USAGE CHECK
        # -----------------------------
        # If c_logo_path is NOT the default one, and we are not forcing default, it means user used a custom logo?
        # Actually in CREATE endpoint, we don't support custom logo upload yet from the UI shown in snippets,
        # but if we did/will:
        # For now, create endpoint primarily uses default logo if plan allows styling is false.
        # But if plan allows styling, user might want custom logo.
        # IF the Logic above `c_logo_data = None` implies no custom logo is passed in `create` currently?
        # Awaiting user clarification or inspection of `create.ts`.
        # Inspecting `create` in `url_routes.py`: `c_logo_data` is initialized to None.
        # It seems `create` endpoint DOES NOT accept a logo upload currently based on the snippet:
        # `c_logo_data = None` is hardcoded at line 132.
        # So `create` endpoint NEVER consumes "Logo Quota" currently.
        # I will leave this as is for now unless I see logo upload code.
 
 
    # Save to DB only
   
    # Allow frontend to pass plan_name (explicitly requested flow)
    req_plan_name = data.get("plan_name")
    final_plan_name = req_plan_name if req_plan_name else (plan.name if plan else 'Free')
 
    new_url = Urls(
        long=long_url,
        short=short_code,
        user_id=current_user.id,
        qr_code=qr_path,
        title=title,
        is_custom=is_custom_flag,
        plan_name=final_plan_name
    )
    db.session.add(new_url)
 
    # INCREMENT USAGE COUNTERS
    # Always increment link usage
    current_user.usage_links = (current_user.usage_links or 0) + 1
 
    # If QR was also generated, increment QR usage too
    if generate_qr:
         current_user.usage_qrs = (current_user.usage_qrs or 0) + 1
   
    db.session.add(current_user)
    db.session.commit()
 
    # ❌ No Redis write here
 
    result = {
        "title": title,
        "long_url": long_url,
        "short_url": short_full,
        "created_at": new_url.created_at.isoformat()
    }
 
    if qr_path:
        result["qr_code"] = build_static_url(qr_path)
 
    return api_response(True, "Short URL created successfully.", result)
 
 
 
 
 
@url_bp.route('/<short_url>')
def redirection(short_url):
    # -------------------------------------
    # 1) Try Redis first
    # -------------------------------------
    cached = None
    long_url = None
    url_id = None
    url_entry = None
 
    try:
        if extensions.redis_client:
            cached = extensions.redis_client.get(f"short:{short_url}")
            print(">>> Redis GET:", cached)
    except:
        cached = None
 
    if cached:
        # Redis HIT
        try:
            payload = json.loads(cached)
            long_url = payload.get("long")
            url_id = payload.get("id")          # using id_
        except:
            # If JSON failed, assume raw string
            long_url = cached
            url_id = None
 
    else:
        # Redis MISS → fallback to DB
        url_entry = Urls.query.filter_by(short=short_url).first()
        if not url_entry:
            return api_response(False, "URL does not exist", None)
 
        long_url = url_entry.long
        url_id = url_entry.id_                 # using id_
 
        # Store in Redis (best effort)
        try:
            ttl = int(current_app.config.get("REDIS_TTL", 3600))
            if extensions.redis_client:
                extensions.redis_client.setex(
                    f"short:{url_entry.short}",
                 # f"short:{short_url}",
 
                    ttl,
                    json.dumps({"long": long_url, "id": url_id})
                )
                print(">>> Redis SET short:" + short_url)
        except:
            pass
 
    # -------------------------------------
    # 2) Parse User-Agent (browser/OS)
    # -------------------------------------
    user_agent_str = request.headers.get("User-Agent", "Unknown")
    ua = parse(user_agent_str)
 
    browser = ua.browser.family or "Unknown"
    browser_version = ua.browser.version_string or "Unknown"
    os_family = ua.os.family or "Unknown"
    os_version = ua.os.version_string or ""
    platform = f"{os_family} {os_version}".strip()
 
    # -------------------------------------
    # 3) Find IP & Location
    # -------------------------------------
    xff = request.headers.get("X-Forwarded-For", '')
    ip_address = xff.split(',')[0].strip() if xff else request.remote_addr or "0.0.0.0"
 
    location = get_location_from_ip(ip_address)
    country = location.get("country")
    region = location.get("region")
    city = location.get("city")
 
    # -------------------------------------
    # 4) Source tracking
    # -------------------------------------
    source = request.args.get("source", "direct")
 
    # -------------------------------------
    # 5) Skip bot requests
    # -------------------------------------
    bot_keywords = [
        "bot", "crawler", "spider", "preview", "fetch", "scan",
        "safelinks", "teams", "outlook", "skype", "microsoft office",
        "linkexpander", "slackbot", "discordbot", "whatsapp", "facebook",
        "twitterbot", "google-read-aloud"
    ]
 
    if any(b in user_agent_str.lower() for b in bot_keywords):
        print(f">>> BOT skipped: {user_agent_str}")
        return redirect(long_url, code=302)
   
#added these for double hits come at a time in mobile
 
    try:
        if extensions.redis_client:
            ua_hash = hash(user_agent_str)
            debounce_key = f"click:{short_url}:{ip_address}:{ua_hash}"
 
            # duplicate click → don't count again
            if extensions.redis_client.get(debounce_key):
                return redirect(long_url, code=302)
 
            # block duplicates for 2 seconds
            extensions.redis_client.setex(debounce_key, 2, "1")
    except:
        pass
# end of addition(up to these lines)
 
    # -------------------------------------
    # 6) Save analytics (only valid traffic)
    # -------------------------------------
    try:
        if url_id is not None:
            analytics = UrlAnalytics(
                url_id=url_id,
                user_agent=user_agent_str,
                browser=browser,
                browser_version=browser_version,
                platform=platform,
                os=os_family,
                ip_address=ip_address,
                country=country,
                region=region,
                city=city,
                source=source
            )
            db.session.add(analytics)
            db.session.commit()
    except Exception as e:
        print(">>> Analytics error:", e)
        try:
            db.session.rollback()
        except:
            pass
 
    # -------------------------------------
    # 7) Redirect to the long URL
    # -------------------------------------
    return redirect(long_url, code=302)
 
 
 
@url_bp.route('/analytics/<short_url>')
@token_required
def get_analytics(current_user, short_url):
    url_entry = Urls.query.filter_by(short=short_url, user_id=current_user.id).first()
    if not url_entry:
        return api_response(False, "URL not found or not yours", None)
 
    # -----------------------------
    # SUBSCRIPTION ANALYTICS CHECK
    # -----------------------------
    plan = current_user.plan
    if plan:
        if not current_user.get_limit('allow_analytics'):
            return api_response(False, "Analytics not allowed on your plan. Please upgrade.", None)
 
    clicks = UrlAnalytics.query.filter_by(url_id=url_entry.id_).order_by(UrlAnalytics.timestamp.desc()).all()
   
    qr_clicks = sum(1 for c in clicks if c.source == "qr")
    direct_clicks = sum(1 for c in clicks if c.source == "direct")
 
    # Filter based on Analytics Level
    analytics_level = current_user.get_limit('analytics_level') if plan else 'none'
   
    click_data = []
    for c in clicks:
        item = {
            "title": url_entry.title,
            "timestamp": c.timestamp.isoformat(),
            "browser": c.browser,
            "platform": c.platform,
            "source": c.source,
            # Basic fields (Pro/Premium)
            "country": c.country if analytics_level in ['basic', 'detailed'] else None,
        }
       
        # Detailed fields (Premium only)
        if analytics_level == 'detailed':
            item.update({
                "ip_address": c.ip_address,
                "browser_version": c.browser_version,
                "os": c.os,
                "region": c.region,
                "city": c.city,
            })
           
        click_data.append(item)
   
    return api_response(True, "Analytics fetched", {
        "short_url": url_entry.short,
        "long_url": url_entry.long,
        "show_short": url_entry.show_short,
        "created_at": url_entry.created_at.isoformat(),
        "total_clicks": len(clicks),
        "qr_clicks": qr_clicks,
        "direct_clicks": direct_clicks,
        "clicks": click_data
    })
 
 
 
@url_bp.route('/userinfo', methods=['GET'])
@token_required
def display_user_info(current_user):
    plan = current_user.plan
    plan_data = None
    if plan:
        plan_data = {
            "name": plan.name,
            "prices": {"usd": plan.price_usd, "inr": plan.price_inr},
            "limits": {
                "max_links": current_user.get_limit("max_links"),
                "max_qrs": current_user.get_limit("max_qrs"),
                "max_custom_links": current_user.get_limit("max_custom_links"),
                "max_qr_with_logo": current_user.get_limit("max_qr_with_logo"),
                "max_editable_links": current_user.get_limit("max_editable_links")
            },
            "permissions": {
                "allow_qr_styling": current_user.get_limit("allow_qr_styling"),
                "allow_analytics": current_user.get_limit("allow_analytics"),
                "show_individual_stats": current_user.get_limit("show_individual_stats"),
                "allow_api_access": current_user.get_limit("allow_api_access"),
                "analytics_level": current_user.get_limit("analytics_level")
            }
        }
 
    return api_response(True, "user Details", {
        "user": {
            "id": current_user.id,
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "email": current_user.email,
            "organization": current_user.organization,
            "password": current_user.password,
            "phone": current_user.phone,
            "client_id": current_user.client_id if (plan and current_user.get_limit('allow_api_access')) else None,
            "client_secret": current_user.client_secret if (plan and current_user.get_limit('allow_api_access')) else None,
            "created_at": current_user.created_at.isoformat(),
            "usage_links": current_user.usage_links or 0,
            "usage_qrs": current_user.usage_qrs or 0,
            "usage_qr_with_logo": current_user.usage_qr_with_logo or 0,
            "plan_details": plan_data  # Added plan details
        }
    })
 
 
@url_bp.route('/update-password', methods=['POST'])
@token_required
def update_password(current_user):
    data = request.get_json() or {}
    current_password = data.get("current_password")
    new_password = data.get("new_password")
 
    if not current_password or not new_password:
        return api_response(False, "Both current and new passwords are required.", None)
 
    is_valid, _ = verify_and_upgrade_password(current_user.password, current_password)
    if not is_valid:
        return api_response(False, "Incorrect current password.", None)
 
    # Prevent reusing the same password
    try:
        same_as_current = check_password_hash(current_user.password, new_password)
    except ValueError:
        # Stored hash might be plaintext legacy; compare directly
        same_as_current = (current_user.password == new_password)
    if same_as_current:
        return api_response(False, "New password cannot be the same as current password. Please choose a different one.", None)
 
    current_user.password = generate_password_hash(new_password)
    db.session.add(current_user)
    db.session.commit()
    return api_response(True, "Password updated successfully.", None)
 
 
@url_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    email = data.get("email")
    if not email:
        return api_response(False, "Email is required", None)
    user = User.query.filter_by(email=email).first()
    if not user:
        return api_response(False, "Email not registered", None)
    return api_response(True, "Email exists, proceed to reset.", None)
 
 
@url_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json() or {}
    email = data.get("email")
    new_password = data.get("password")
    if not email or not new_password:
        return api_response(False, "Email and password are required", None)
 
    user = User.query.filter_by(email=email).first()
    if not user:
        return api_response(False, "User not found.", None)
 
    user.password = generate_password_hash(new_password)
    db.session.add(user)
    db.session.commit()
    return api_response(True, "Password updated successfully.", None)
 
 
@url_bp.route('/myurls', methods=['GET'])
@token_required
def my_urls(current_user):
    urls = Urls.query.filter_by(user_id=current_user.id).all()
    base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")
    return api_response(True, "sending All url details", {
        "user_id": current_user.id,
        "urls": [
            {
                "title": u.title,
                "shorturl": f"{base_url}/{u.short}" if u.short else None,
                "shortcode": u.short,
                "long": u.long,
                "created_at": u.created_at.isoformat(),
                "qr_code": build_static_url(u.qr_code),
                "show_short": u.show_short,
                "hits": UrlAnalytics.query.filter_by(url_id=u.id_).count()  # ✅ ADD THIS
            }
            for u in urls
        ],
    })
 
 
 
@url_bp.route('/urlcount', methods=['GET'])
@token_required
def url_count(current_user):
    count = Urls.query.filter_by(user_id=current_user.id).count()
    return api_response(True, "URL count", {
        "user_id": current_user.id,
        "total_urls": count
    })
 
 
@url_bp.route('/delete/<short_url>', methods=['DELETE'])
@token_required
def delete_url(current_user, short_url):
    url_entry = Urls.query.filter_by(short=short_url, user_id=current_user.id).first()
    if not url_entry:
        return api_response(False, "URL not found or you don't have permission to delete", None)
 
    # ✔ Convert relative QR path to absolute
    if url_entry.qr_code:
        file_path = absolute_qr_path(url_entry.qr_code)
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                current_app.logger.warning(f"Failed to delete QR file: {e}")
 
    # ✔ Delete analytics
    UrlAnalytics.query.filter_by(url_id=url_entry.id_).delete()
 
    # ✔ Delete URL
    db.session.delete(url_entry)
    db.session.commit()
 
    # Remove from Redis cache (best-effort)
    try:
        if extensions.redis_client:
            extensions.redis_client.delete(f"short:{short_url}")
    except Exception:
        pass
 
    return api_response(True, f"Short URL '{short_url}' deleted successfully.", None)
 
import datetime
import pytz
from sqlalchemy import and_
 
@url_bp.route('/totalclicks', methods=['GET'])
@token_required
def dashboard_stats(current_user):
    urls = Urls.query.filter_by(user_id=current_user.id).all()
    url_ids = [u.id_ for u in urls]
 
    total_links = len(urls)
 
    if not url_ids:
        total_clicks = 0
        clicks_today = 0
    else:
        total_clicks = UrlAnalytics.query.filter(
            UrlAnalytics.url_id.in_(url_ids)
        ).count()
 
        # -----------------------------
        # FIX: IST TIME RANGE FOR TODAY
        # -----------------------------
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.datetime.now(ist)
 
        # today's date in IST
        today_ist = now_ist.date()
 
        # start and end of the IST day (converted to UTC for querying DB)
        start_ist = ist.localize(datetime.datetime(today_ist.year, today_ist.month, today_ist.day, 0, 0, 0))
        end_ist = start_ist + datetime.timedelta(days=1)
 
        start_utc = start_ist.astimezone(pytz.utc)
        end_utc = end_ist.astimezone(pytz.utc)
 
        # Query UTC timestamps using the calculated range
        clicks_today = UrlAnalytics.query.filter(
            UrlAnalytics.url_id.in_(url_ids),
            UrlAnalytics.timestamp >= start_utc,
            UrlAnalytics.timestamp < end_utc
        ).count()
 
    # your new fields (unchanged)
    total_short_links = Urls.query.filter_by(
        user_id=current_user.id,
        show_short=True
    ).count()
 
    total_qrs = Urls.query.filter(
        Urls.user_id == current_user.id,
        Urls.qr_code.isnot(None)
    ).count()
 
    return api_response(True, "Dashboard stats", {
        "user_id": current_user.id,
        "total_links": total_links,
        "total_clicks": total_clicks,
        "clicks_today": clicks_today,
        "total_qrs": total_qrs,
        "total_short_links": total_short_links
    })
 
 
 
@url_bp.route('/url/<short_url>', methods=['GET'])
@token_required
def get_url_details(current_user, short_url):
    url_entry = Urls.query.filter_by(short=short_url, user_id=current_user.id).first()
    if not url_entry:
        return api_response(False, "URL not found", None)
 
    return api_response(True, "URL details", {
        "title": url_entry.title,
        "short_url": url_entry.short,
        "long_url": url_entry.long,
        "qr_code": url_entry.qr_code,
        "created_at": url_entry.created_at.isoformat(),
    })
 
@url_bp.route('/edit', methods=['PUT'])
@token_required
def edit_short_url(current_user):
    import os
 
    try:
        data = request.get_json()
        old_short = data.get("old_short")
        new_short = data.get("new_short")
 
        if not old_short or not new_short:
            return api_response(False, "Missing fields", None)
 
        if not new_short.isalnum():
            return api_response(False, "Short code must be alphanumeric", None)
 
        if Urls.query.filter_by(short=new_short).first():
            return api_response(False, "Short URL already exists", None)
 
        url = Urls.query.filter_by(short=old_short, user_id=current_user.id).first()
        if not url:
            return api_response(False, "Old short URL not found", None)
 
        # -----------------------------
        # SUBSCRIPTION EDIT LIMIT
        # -----------------------------
        if current_user.plan:
             limit_editable = current_user.get_limit('max_editable_links')
             if limit_editable != -1:
                 if not url.is_edited:
                     edited_count = Urls.query.filter_by(user_id=current_user.id, is_edited=True).count()
                     if edited_count >= limit_editable:
                          return api_response(False, f"Edit limit reached ({limit_editable}). Upgrade to edit more links.", None)
 
        base_url = current_app.config.get("BASE_URL")
 
        # CASE 1: URL HAS QR → regenerate
        if url.qr_code:
            old_qr_path = absolute_qr_path(url.qr_code)
            if old_qr_path and os.path.exists(old_qr_path):
                try:
                    os.remove(old_qr_path)
                except:
                    pass
           
            # Determine logo source
            r_logo_data = url.logo
            r_logo_path = None
           
            if current_user.plan and not current_user.get_limit('allow_qr_styling'):
                 # Enforce default logo
                 default_logo = os.path.join(current_app.static_folder or "static", "image.png")
                 if os.path.exists(default_logo):
                      r_logo_path = default_logo
                 r_logo_data = None
 
            static_rel = generate_styled_qr(
                short_code=new_short,
                color_dark=url.color_dark or "#000000",
                style=url.style or "square",
                logo_data=r_logo_data,
                logo_path=r_logo_path
            )
           
            # Increment usage if this is the first edit
            if not url.is_edited:
                 current_user.usage_editable_links = (current_user.usage_editable_links or 0) + 1
                 db.session.add(current_user)
 
            # Update DB
            url.short = new_short
            url.qr_code = static_rel
            url.is_edited = True
            db.session.commit()
       
           
       
            # NEW ✔ Delete old key from Redis
            try:
                if extensions.redis_client:
                    extensions.redis_client.delete(f"short:{old_short}")
            except:
                pass
 
            return api_response(True, "Short URL updated (QR regenerated)", {
                "newShortUrl": f"{base_url}/{new_short}",
                "newQrCode": build_static_url(static_rel)
            })
 
        # CASE 2: No QR → simple update
        else:
            url.short = new_short
            url.is_edited = True
            db.session.commit()
 
            # NEW ✔ Delete old key from Redis
            try:
                if extensions.redis_client:
                    extensions.redis_client.delete(f"short:{old_short}")
            except:
                pass
 
            return api_response(True, "Short URL updated successfully", {
                "newShortUrl": f"{base_url}/{new_short}"
            })
 
    except Exception as e:
        db.session.rollback()
        return api_response(False, str(e), None)
 
 
 
 
 
 
@url_bp.route('/delete-account', methods=['DELETE'])
@token_required
def delete_account(current_user):
    try:
        # ----------------------------------------------
        # 1. Collect all user's URLs
        # ----------------------------------------------
        urls = Urls.query.filter_by(user_id=current_user.id).all()
        url_ids = [u.id_ for u in urls]
        short_codes = [u.short for u in urls]
 
        # ----------------------------------------------
        # 2. Delete analytics records
        # ----------------------------------------------
        if url_ids:
            UrlAnalytics.query.filter(
                UrlAnalytics.url_id.in_(url_ids)
            ).delete(synchronize_session=False)
 
        # ----------------------------------------------
        # 3. Delete QR image files
        # ----------------------------------------------
        for u in urls:
            if u.qr_code:
                path = absolute_qr_path(u.qr_code)
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        current_app.logger.warning(f"QR deletion failed: {e}")
 
        # ----------------------------------------------
        # 4. Delete Redis keys
        # ----------------------------------------------
        try:
            if extensions.redis_client:
                for s in short_codes:
                    extensions.redis_client.delete(f"short:{s}")
        except Exception as e:
            current_app.logger.warning(f"Redis cleanup failed: {e}")
 
        # ----------------------------------------------
        # 5. Delete URL records
        # ----------------------------------------------
        if url_ids:
            Urls.query.filter(
                Urls.id_.in_(url_ids)
            ).delete(synchronize_session=False)
 
        # ----------------------------------------------
        # 6. Delete the user
        # ----------------------------------------------
        db.session.delete(current_user)
        db.session.commit()
 
        return api_response(True, "Account and all related data deleted successfully.", None)
 
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Account deletion error: {e}")
        return api_response(False, "Failed to delete account.", None)
@url_bp.route('/generate-qr', methods=['POST'])
@token_required
def generate_qr(current_user):
    import uuid, os, io, base64, json
    from urllib.parse import urlparse
 
    data = request.get_json(silent=True) or {}
 
    long_url = (data.get("long_url") or "").strip()
    show_short = bool(data.get("generate_short", False))
    color_dark = (data.get("color_dark") or "#000000").strip()
    style = (data.get("style") or "square").strip().lower()
    custom_short = (data.get("custom") or "").strip()
    logo_data = data.get("logo")
    title = (data.get("title") or "").strip()
 
    if not long_url:
        return api_response(False, "long_url is required", None)
 
    parsed = urlparse(long_url)
    if not parsed.scheme:
        long_url = "https://" + long_url
 
    # -----------------------------
    # SUBSCRIPTION LIMIT CHECK (CONSUMPTION STRICT)
    # -----------------------------
    plan = current_user.plan
    if plan:
        # 1. QR Limit (Always)
        limit_qrs = current_user.get_limit('max_qrs')
        if limit_qrs != -1 and current_user.usage_qrs >= limit_qrs:
             return api_response(False, f"QR code limit reached ({limit_qrs}). Please upgrade.", None)
       
        # 2. Link Limit (Only if generate_short is requested)
        if show_short:
             limit_links = current_user.get_limit('max_links')
             if limit_links != -1 and current_user.usage_links >= limit_links:
                  return api_response(False, f"Link creation limit reached ({limit_links}). Upgrade to use Short Link feature with QR.", None)
       
        # 3. Logo Limit (If logo is provided)
        if logo_data:
             limit_logo = current_user.get_limit('max_qr_with_logo')
             if limit_logo != -1 and current_user.usage_qr_with_logo >= limit_logo:
                  return api_response(False, f"Logo limit reached ({limit_logo}). You can only create {limit_logo} QRs with custom logos.", None)
       
        # 3. Custom Slug Limit (if applicable)
        if custom_short:
            current_custom_count = Urls.query.filter_by(user_id=current_user.id, is_custom=True).count()
            limit_custom = current_user.get_limit('max_custom_links')
            if current_custom_count >= limit_custom:
                return api_response(False, f"Custom link limit reached ({limit_custom}). Please upgrade.", None)
 
    base_url = current_app.config.get("BASE_URL")
 
    # Short code logic
    if custom_short:
        if not custom_short.isalnum():
            return api_response(False, "Custom short URL must be alphanumeric.", None)
        if Urls.query.filter_by(short=custom_short).first():
            return api_response(False, "This custom short URL is already taken.", None)
        short_code = custom_short
    else:
        short_code = _shorten_url()
 
    # QR encodes short URL
    # (Removed manual QR generation code block)
 
    # Defaults
    logo_path_arg = None
   
    # Enforce default logo for Free plan (or if styling not allowed)
    if plan and not current_user.get_limit('allow_qr_styling'):
        # User cannot customize style or logo, but we enforce the default branding
        default_logo = os.path.join(current_app.static_folder or "static", "image.png")
        if os.path.exists(default_logo):
             logo_path_arg = default_logo
        # Ensure custom logo is ignored
        logo_data = None
   
    # Use shared utility
    static_rel = generate_styled_qr(short_code, color_dark, style, logo_data, logo_path=logo_path_arg)
   
    # Save to DB only
   
    # Allow frontend to pass plan_name
    req_plan_name = data.get("plan_name")
    final_plan_name = req_plan_name if req_plan_name else (plan.name if plan else 'Free')
 
    new_url = Urls(
        long=long_url,
        short=short_code,
        user_id=current_user.id,
        qr_code=static_rel,
        show_short=show_short,
        color_dark=color_dark,
        style=style,
        logo=logo_data,
        title=title,
        is_custom=bool(custom_short),
        is_edited=False,
        plan_name=final_plan_name
    )
 
    db.session.add(new_url)
   
    # INCREMENT USAGE
    # Always increment QR usage
    current_user.usage_qrs = (current_user.usage_qrs or 0) + 1
   
    # If Short URL was requested (checkbox), increment Link usage too
    if show_short:
        current_user.usage_links = (current_user.usage_links or 0) + 1
 
    # If Logo was used, increment Logo usage
    if logo_data:
        current_user.usage_qr_with_logo = (current_user.usage_qr_with_logo or 0) + 1
       
    db.session.add(current_user)
 
    db.session.commit()
 
    # ❌ Do NOT write to Redis
 
    data = {
        "title": title,
        "long_url": long_url,
        "qr_code": build_static_url(static_rel),
        "created_at": new_url.created_at.isoformat(),
        "show_short": show_short,
    }
 
    if show_short:
        data["short_url"] = f"{base_url}/{short_code}"
 
    return api_response(True, "QR code generated successfully.", data)
 
 
 
 
@url_bp.route('/test-ip', methods=['POST'])
def test_ip():
    """
    Test IP → Geo lookup using JSON body.
    Example JSON:
    {
        "ip": "8.8.8.8"
    }
    """
    data = request.get_json(silent=True) or {}
    ip = (data.get("ip") or "").strip()
 
    if not ip:
        return api_response(False, "JSON body must include 'ip'", None)
 
    location = get_location_from_ip(ip)
 
    return api_response(True, "IP lookup successful", {
        "ip": ip,
        "country": location.get("country"),
        "region": location.get("region"),
        "city": location.get("city")
    })
 
 
 
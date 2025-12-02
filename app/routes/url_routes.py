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
import qrcode
from PIL import Image
from app.extensions import db, redis_client

# from ..extensions import db, redis_client
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
 
from .. import extensions
 
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
 
 
def _generate_qr_code(short_code: str) -> str:
    qr_dir = current_app.static_folder and os.path.join(current_app.static_folder, "qrcodes") or "static/qrcodes"
    os.makedirs(qr_dir, exist_ok=True)
 
    base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")
    short_url_full = f"{base_url}/{short_code}"
 
    qr_filename = f"{short_code}_{uuid.uuid4().hex}.png"
    qr_path = os.path.join(qr_dir, qr_filename)
 
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(short_url_full)
    qr.make(fit=True)
 
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
 
    logo_path = "static/image.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path)
        qr_width, qr_height = qr_img.size
        logo_size = int(qr_width * 0.25)
        logo = logo.resize((logo_size, logo_size))
 
        padding = 10
        padded_size = (logo_size + padding * 2, logo_size + padding * 2)
        padded_logo = Image.new("RGB", padded_size, "white")
        padded_logo.paste(logo, (padding, padding), mask=logo if logo.mode == "RGBA" else None)
 
        pos = ((qr_width - padded_size[0]) // 2, (qr_height - padded_size[1]) // 2)
        qr_img.paste(padded_logo, pos)
 
    qr_img.save(qr_path)
 
    # Return a path relative to /static for URL building
    static_rel = os.path.relpath(qr_path, start=current_app.static_folder or "static")
    return static_rel.replace("\\", "/")
 
 
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
    from ..utils.plan_checker import check_plan_limits
    data = request.get_json() or {}

    long_url = (data.get("long_url") or "").strip()
    custom_short = (data.get("custom") or "").strip()
    generate_qr = bool(data.get("generate_qr", False))
    title = (data.get("title") or "").strip()

    if not long_url:
        return api_response(False, "long_url is required", None)

    # Normalize long URL
    parsed = urlparse(long_url)
    if not parsed.scheme:
        long_url = "https://" + long_url

    # Determine limit usage
    will_create_custom = bool(custom_short)
    will_create_qr = bool(generate_qr)
    will_create_short = True  # Always true for /create

    # LIMIT CHECK (Bitly-style permanent limits)
    ok, msg = check_plan_limits(
        current_user,
        will_create_short=will_create_short,
        will_create_qr=will_create_qr,
        will_create_custom=will_create_custom
    )
    if not ok:
        return api_response(False, msg, None)

    # Generate short code
    if custom_short:
        if not custom_short.isalnum():
            return api_response(False, "Custom short URL must be alphanumeric", None)
        if Urls.query.filter_by(short=custom_short).first():
            return api_response(False, "This custom short URL already exists.", None)
        short_code = custom_short
        is_custom = True
    else:
        short_code = _shorten_url()
        is_custom = False

    base_url = current_app.config.get("BASE_URL")
    short_full = f"{base_url}/{short_code}"

    # Generate QR code
    qr_path = _generate_qr_code(short_code) if generate_qr else None

    # Save URL record
    new_url = Urls(
        long=long_url,
        short=short_code,
        user_id=current_user.id,
        qr_code=qr_path,
        title=title,
        custom=is_custom,
        qr_generated=bool(generate_qr)
    )
    db.session.add(new_url)
    db.session.commit()

    # ------------------------------------------------------------
    # ⭐ Permanent usage counters — DOES NOT DECREASE ON DELETE
    # ------------------------------------------------------------
    try:
        current_user.total_links_created += 1
        if is_custom:
            current_user.total_custom_created += 1
        if generate_qr:
            current_user.total_qr_created += 1
        db.session.commit()
    except:
        db.session.rollback()

    # Save Redis cache (optional)
    try:
        ttl = int(current_app.config.get("REDIS_TTL", 3600))
        if extensions.redis_client:
            extensions.redis_client.setex(
                f"short:{short_code}", ttl,
                json.dumps({"long": long_url, "id": new_url.id_})
            )
    except:
        pass

    # Response
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
        try:
            payload = json.loads(cached)
            long_url = payload.get("long")
            url_id = payload.get("id")
        except:
            long_url = cached
            url_id = None

    else:
        url_entry = Urls.query.filter_by(short=short_url).first()
        if not url_entry:
            return api_response(False, "URL does not exist", None)

        long_url = url_entry.long
        url_id = url_entry.id_

        try:
            ttl = int(current_app.config.get("REDIS_TTL", 3600))
            if extensions.redis_client:
                extensions.redis_client.setex(
                    f"short:{short_url}",
                    ttl,
                    json.dumps({"long": long_url, "id": url_id})
                )
                print(">>> Redis SET:", short_url)
        except:
            pass

    # -------------------------------------
    # 2) Parse User-Agent
    # -------------------------------------
    user_agent_str = request.headers.get("User-Agent", "Unknown")
    ua = parse(user_agent_str)

    browser = ua.browser.family or "Unknown"
    browser_version = ua.browser.version_string or "Unknown"
    os_family = ua.os.family or "Unknown"
    os_version = ua.os.version_string or ""
    platform = f"{os_family} {os_version}".strip()

    # -------------------------------------
    # 3) IP + Location
    # -------------------------------------
    xff = request.headers.get("X-Forwarded-For", "")
    ip_address = xff.split(',')[0].strip() if xff else request.remote_addr or "0.0.0.0"

    location = get_location_from_ip(ip_address)
    country = location.get("country")
    region = location.get("region")
    city = location.get("city")

    # -------------------------------------
    # 4) Tracking source
    # -------------------------------------
    source = request.args.get("source", "direct")

    # -------------------------------------
    # 5) Skip BOT requests
    # -------------------------------------
    bot_keywords = [
        "bot", "crawler", "spider", "preview", "fetch", "scan",
        "safelinks", "teams", "outlook", "skype", "microsoft office",
        "linkexpander", "slackbot", "discordbot", "whatsapp", "facebook",
        "twitterbot", "google-read-aloud"
    ]

    if any(b in user_agent_str.lower() for b in bot_keywords):
        print(f">>> BOT skipped analytics: {user_agent_str}")
        return redirect(long_url, code=302)

    # -------------------------------------
    # 6) Analytics logic (LIMIT = 7 hits)
    # -------------------------------------
    try:
        from ..utils.plan_checker import (
            link_analytics_allowed,
            enforce_analytics_limits
        )

        if not url_entry:
            url_entry = Urls.query.filter_by(short=short_url).first()

        # Per-link analytics limit reached
        if not link_analytics_allowed(url_id, url_entry.user):

            print(">>> Analytics limit reached for this link (7 hits). No analytics saved.")

            return api_response(
                False,
                "Analytics limit reached for this link (7 hits).",
                {"long_url": long_url}
            )

        # Save analytics (HIT COUNT < 7)
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

        enforce_analytics_limits(url_entry.user)

    except Exception as e:
        print(">>> Analytics error:", e)
        try:
            db.session.rollback()
        except:
            pass

    # -------------------------------------
    # 7) Redirect user to long URL
    # -------------------------------------
    return redirect(long_url, code=302)


 
@url_bp.route('/analytics/<short_url>')
@token_required
def get_analytics(current_user, short_url):

    # 🚫 Block analytics for free plan
    if getattr(current_user, "plan", "free") == "free":
        return api_response(False, "Analytics are not available on the Free plan.", None)

    url_entry = Urls.query.filter_by(short=short_url, user_id=current_user.id).first()
    if not url_entry:
        return api_response(False, "URL not found or not yours", None)

    clicks = UrlAnalytics.query.filter_by(url_id=url_entry.id_).order_by(UrlAnalytics.timestamp.desc()).all()
   
    qr_clicks = sum(1 for c in clicks if c.source == "qr")
    direct_clicks = sum(1 for c in clicks if c.source == "direct")
   
    return api_response(True, "Analytics fetched", {
        "short_url": url_entry.short,
        "long_url": url_entry.long,
        "show_short": url_entry.show_short,
        "created_at": url_entry.created_at.isoformat(),
        "total_clicks": len(clicks),
        "qr_clicks": qr_clicks,
        "direct_clicks": direct_clicks,
        "clicks": [
            {
                "title": url_entry.title,
                "timestamp": c.timestamp.isoformat(),
                "ip_address": c.ip_address,
                "browser": c.browser,
                "browser_version": c.browser_version,
                "platform": c.platform,
                "os": c.os,
                "country": c.country,
                "region": c.region,
                "city": c.city,
                "source": c.source,
            }
            for c in clicks
        ]
    })

 
 
@url_bp.route('/userinfo', methods=['GET'])
@token_required
def display_user_info(current_user):
    return api_response(True, "user Details", {
        "user": {
            "id": current_user.id,
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "email": current_user.email,
            "organization": current_user.organization,
            "password": current_user.password,
            "phone": current_user.phone,
            "client_id": current_user.client_id,
            "client_secret": current_user.client_secret,
            "created_at": current_user.created_at.isoformat()
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
    from PIL import Image, ImageColor
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import (
        SquareModuleDrawer, GappedSquareModuleDrawer,
        CircleModuleDrawer, RoundedModuleDrawer
    )
    from qrcode.image.styles.colormasks import SolidFillColorMask
    import io, base64, uuid, os

    from ..utils.plan_checker import can_edit_short_link

    # ✅ Correct plan check (handles free/pro/enterprise)
    ok, msg = can_edit_short_link(current_user)
    if not ok:
        return api_response(False, msg, None)

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

        base_url = current_app.config.get("BASE_URL")

        # CASE 1: URL HAS QR → regenerate
        if url.qr_code:

            old_qr_path = absolute_qr_path(url.qr_code)

            if old_qr_path and os.path.exists(old_qr_path):
                try:
                    os.remove(old_qr_path)
                except:
                    pass

            qr_data = f"{base_url}/{new_short}?source=qr"
            qr_dir = os.path.join(current_app.static_folder or "static", "qrcodes")
            os.makedirs(qr_dir, exist_ok=True)

            qr_filename = f"qr_{uuid.uuid4().hex}.png"
            qr_path = os.path.join(qr_dir, qr_filename)

            color_dark = url.color_dark or "#000000"
            style = (url.style or "square").lower()

            try:
                fill_rgb = ImageColor.getrgb(color_dark)
            except:
                fill_rgb = (0, 0, 0)

            back_rgb = (255, 255, 255)

            drawer_map = {
                "square": SquareModuleDrawer(),
                "dots": GappedSquareModuleDrawer(),
                "circle": CircleModuleDrawer(),
                "rounded": RoundedModuleDrawer(),
            }
            drawer = drawer_map.get(style, SquareModuleDrawer())

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            qr_img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=drawer,
                color_mask=SolidFillColorMask(
                    back_color=back_rgb, front_color=fill_rgb
                )
            ).convert("RGB")

            try:
                logo = None
                if url.logo:
                    logo_data = url.logo.split(",", 1)[1] if "," in url.logo else url.logo
                    logo_bytes = base64.b64decode(logo_data)
                    logo = Image.open(io.BytesIO(logo_bytes))

                default_logo_path = os.path.join("static", "image.png")
                if not logo and os.path.exists(default_logo_path):
                    logo = Image.open(default_logo_path)

                if logo:
                    qr_w, qr_h = qr_img.size
                    size = int(qr_w * 0.25)
                    logo = logo.resize((size, size))
                    pos = ((qr_w - size) // 2, (qr_h - size) // 2)
                    qr_img.paste(logo, pos)

            except Exception as e:
                current_app.logger.warning(f"Logo embed error: {e}")

            qr_img.save(qr_path)
            static_rel = os.path.relpath(qr_path, start=current_app.static_folder or "static").replace("\\", "/")

            url.short = new_short
            url.qr_code = static_rel
            db.session.commit()

            # ✅ Increment edit count (use DB-level update to ensure persistence)
            try:
                User.query.filter_by(id=current_user.id).update({"edit_count": User.edit_count + 1})
                db.session.commit()
            except Exception:
                db.session.rollback()

            try:
                if redis_client:
                    ttl = int(current_app.config.get("REDIS_TTL", 3600))
                    redis_client.delete(f"short:{old_short}")
                    redis_client.setex(f"short:{new_short}", ttl,
                        json.dumps({"long": url.long, "id": getattr(url, 'id_', None)})
                    )
            except Exception:
                pass

            return api_response(True, "Short URL updated successfully (QR regenerated)", {
                "newShortUrl": f"{base_url}/{new_short}",
                "newQrCode": build_static_url(static_rel)
            })

        # ---------------------------------------------------------
        # CASE 2: NO QR → JUST UPDATE SHORT
        # ---------------------------------------------------------
        else:
            url.short = new_short
            db.session.commit()

            # ✅ Increment edit count (use DB-level update to ensure persistence)
            try:
                User.query.filter_by(id=current_user.id).update({"edit_count": User.edit_count + 1})
                db.session.commit()
            except Exception:
                db.session.rollback()

            try:
                if redis_client:
                    ttl = int(current_app.config.get("REDIS_TTL", 3600))
                    redis_client.delete(f"short:{old_short}")
                    redis_client.setex(f"short:{new_short}", ttl,
                        json.dumps({"long": url.long, "id": getattr(url, 'id_', None)})
                    )
            except Exception:
                pass

            return api_response(True, "Short URL updated successfully (no QR generated)", {
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
            if redis_client:
                for s in short_codes:
                    redis_client.delete(f"short:{s}")
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
    """
    Generate a QR Code (Bitly-style)
    Short link generated only if requested (show_short=True)
    Permanent limits apply — delete does NOT free usage.
    """
    import qrcode
    from PIL import Image, ImageColor
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import (
        SquareModuleDrawer, GappedSquareModuleDrawer,
        CircleModuleDrawer, RoundedModuleDrawer
    )
    from qrcode.image.styles.colormasks import SolidFillColorMask
    import base64, io, uuid, os
    from urllib.parse import urlparse

    from ..utils.plan_checker import check_plan_limits

    data = request.get_json(silent=True) or {}

    long_url = (data.get("long_url") or "").strip()
    show_short = bool(data.get("generate_short", False) or data.get("show_short", False))
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

    base_url = current_app.config.get("BASE_URL")

    # Determine limit usage
    will_create_qr = True
    will_create_short = bool(show_short)
    will_create_custom = bool(custom_short)

    # LIMIT CHECK (Bitly-style permanent limits)
    ok, msg = check_plan_limits(
        current_user,
        will_create_short=will_create_short,
        will_create_qr=will_create_qr,
        will_create_custom=will_create_custom
    )
    if not ok:
        return api_response(False, msg, None)

    # Short code selection
    if custom_short:
        if not custom_short.isalnum():
            return api_response(False, "Custom short URL must be alphanumeric.", None)
        if Urls.query.filter_by(short=custom_short).first():
            return api_response(False, "Custom short code already exists.", None)
        short_code = custom_short
        is_custom = True
    else:
        short_code = _shorten_url()
        is_custom = False

    # QR points to short link for analytics
    qr_data = f"{base_url}/{short_code}?source=qr"

    # Image path setup
    qr_dir = os.path.join(current_app.static_folder or "static", "qrcodes")
    os.makedirs(qr_dir, exist_ok=True)

    qr_filename = f"qr_{uuid.uuid4().hex}.png"
    qr_path = os.path.join(qr_dir, qr_filename)

    # QR styling
    try:
        fill_rgb = ImageColor.getrgb(color_dark)
    except:
        fill_rgb = (0, 0, 0)

    back_rgb = (255, 255, 255)

    drawer_map = {
        "square": SquareModuleDrawer(),
        "dots": GappedSquareModuleDrawer(),
        "circle": CircleModuleDrawer(),
        "rounded": RoundedModuleDrawer(),
        "vertical-bars": GappedSquareModuleDrawer(),
        "horizontal-bars": GappedSquareModuleDrawer(),
        "mosaic": CircleModuleDrawer(),
        "beads": RoundedModuleDrawer(),
    }
    drawer = drawer_map.get(style, SquareModuleDrawer())
    color_mask = SolidFillColorMask(back_color=back_rgb, front_color=fill_rgb)

    # Build QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        color_mask=SolidFillColorMask(back_color=back_rgb, front_color=fill_rgb)
    ).convert("RGB")

    # Logo support
    if logo_data:
        try:
            if "," in logo_data:
                logo_data = logo_data.split(",", 1)[1]
            logo_bytes = base64.b64decode(logo_data)
            logo_img = Image.open(io.BytesIO(logo_bytes))

            qr_w, qr_h = qr_img.size
            size = int(qr_w * 0.25)
            logo_img = logo_img.resize((size, size))
            pos = ((qr_w - size) // 2, (qr_h - size) // 2)
            qr_img.paste(logo_img, pos)
        except Exception as e:
            current_app.logger.warning(f"Logo failed: {e}")

    qr_img.save(qr_path)
    static_rel = os.path.relpath(qr_path, start=current_app.static_folder or "static").replace("\\", "/")

    # Store in DB
    new_url = Urls(
        long=long_url,
        short=short_code,
        user_id=current_user.id,
        qr_code=static_rel,
        show_short=show_short,
        title=title,
        custom=is_custom,
        style=style,
        color_dark=color_dark,
        logo=logo_data,
        qr_generated=True
    )

    db.session.add(new_url)
    db.session.commit()

    # ------------------------------------------------------------
    # ⭐ Permanent counters — delete does NOT reduce usage
    # ------------------------------------------------------------
    try:
        current_user.total_qr_created += 1
        if show_short:
            current_user.total_links_created += 1
        if custom_short:
            current_user.total_custom_created += 1
        db.session.commit()
    except:
        db.session.rollback()

    # Redis cache write
    try:
        if redis_client:
            redis_client.setex(
                f"short:{short_code}",
                int(current_app.config.get("REDIS_TTL", 3600)),
                json.dumps({"long": long_url, "id": new_url.id_})
            )
    except:
        pass

    response = {
        "title": title,
        "long_url": long_url,
        "qr_code": build_static_url(static_rel),
        "created_at": new_url.created_at.isoformat(),
        "show_short": show_short
    }

    if show_short:
        response["short_url"] = f"{base_url}/{short_code}"

    return api_response(True, "QR code generated successfully.", response)





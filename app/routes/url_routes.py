import os
import random
import string
import uuid
import datetime
from urllib.parse import urlparse
 
from flask import Blueprint, logging, request, redirect
import requests
from user_agents import parse
import qrcode
from PIL import Image
 
from ..extensions import db
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
 
 
url_bp = Blueprint("url", __name__)
 
def get_location_from_ip(ip: str | None) -> dict:
    """
    Fetch country, region (state), and city (district) from IP address.
    Returns 'Unknown' if lookup fails.
    """
    ip = ip or ""
    try:
        res = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        if res.status_code == 200:
            data = res.json()
            return {
                "country": data.get("country_name", "Unknown"),
                "region": data.get("region", "Unknown"),  # State / Province
                "city": data.get("city", "Unknown"),      # District / City
            }
    except Exception as e:
        logging.error(f"GeoIP lookup failed: {e}")
 
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
    """
    Always generate a short link for analytics.
    If the user provides a custom short code, use it (if available).
    Optionally generate a QR code if requested.
    """
    data = request.get_json() or {}
 
    long_url = data.get("long_url", "").strip()
    custom_short = data.get("custom", "").strip()
    generate_qr = data.get("generate_qr", False)
    title = (data.get("title") or "").strip()

 
    if not long_url:
        return api_response(False, "long_url is required", None)
 
    # ✅ Ensure valid URL format
    parsed = urlparse(long_url)
    if not parsed.scheme:
        long_url = "https://" + long_url
 
    # ✅ Handle short code logic
    if custom_short:
        if not custom_short.isalnum():
            return api_response(False, "Custom short URL must be alphanumeric.", None)
        existing = Urls.query.filter_by(short=custom_short).first()
        if existing:
            return api_response(False, "This custom short URL is already taken.", None)
        short_code = custom_short
    else:
        short_code = _shorten_url()
 
    base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")
    short_full = f"{base_url}/{short_code}"
 
    # ✅ Optionally generate QR for the short link
    qr_path = _generate_qr_code(short_code) if generate_qr else None
 
    # ✅ Store in DB for analytics
    new_url = Urls(
        long=long_url,
        short=short_code,
        user_id=current_user.id,
        qr_code=qr_path,
        title=title   # ✅ added here

    )
    db.session.add(new_url)
    db.session.commit()
 
    # ✅ Build response
    response_data = {
        "title": title,
        "long_url": long_url,
        "short_url": short_full,
        "created_at": new_url.created_at.isoformat(),
    }
 
    if qr_path:
        response_data["qr_code"] = build_static_url(qr_path)
 
    return api_response(True, "Short URL created successfully.", response_data)
 
 
 
@url_bp.route('/<short_url>')
def redirection(short_url):
    url_entry = Urls.query.filter_by(short=short_url).first()
    if not url_entry:
        return api_response(False, "URL does not exist", None)
 
    user_agent_str = request.headers.get('User-Agent', "Unknown")
    ua = parse(user_agent_str)
 
    browser = ua.browser.family or "Unknown"
    browser_version = ua.browser.version_string or "Unknown"
    os_family = ua.os.family or "Unknown"
    os_version = ua.os.version_string or ""
    platform = f"{os_family} {os_version}".strip()
 
    xff = request.headers.get('X-Forwarded-For', '')
    ip_address = xff.split(',')[0].strip() if xff else request.remote_addr or "0.0.0.0"
    location = get_location_from_ip(ip_address) if ip_address else {"country": "Unknown", "region": "Unknown", "city": "Unknown"}
    country = location["country"]
    region = location["region"]
    city = location["city"]
 
 
    # detect source
    source = request.args.get("source", "direct")
 
    # Skip bots
    bot_keywords = [
        "bot", "crawler", "spider", "preview", "fetch", "scan",
        "SafeLinks", "Teams", "Outlook", "Skype", "Microsoft Office",
        "LinkExpander", "Slackbot", "Discordbot", "WhatsApp", "Facebook",
        "Twitterbot", "Google-Read-Aloud"
    ]
    if any(b.lower() in user_agent_str.lower() for b in bot_keywords):
        print(f"Skipped bot: {user_agent_str}")
        return redirect(url_entry.long, code=302)
 
    try:
        analytics = UrlAnalytics(
            url_id=url_entry.id_,
            user_agent=user_agent_str,
            browser=browser,
            browser_version=browser_version,
            platform=platform,
            os=os_family,
            ip_address=ip_address,
            country=country,
            region=region,  
            city=city,    
            source=source,  # ✅ log QR vs direct
        )
        db.session.add(analytics)
        db.session.commit()
    except Exception:
        db.session.rollback()
 
    return redirect(url_entry.long, code=302)
 
 
 
 
@url_bp.route('/analytics/<short_url>')
@token_required
def get_analytics(current_user, short_url):
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
                "region": c.region,  # ✅ added
                "city": c.city,    
                "source": c.source,
            } for c in clicks
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

    return api_response(True, f"Short URL '{short_url}' deleted successfully.", None)

 
@url_bp.route('/totalclicks', methods=['GET'])
@token_required
def dashboard_stats(current_user):
    urls = Urls.query.filter_by(user_id=current_user.id).all()
    url_ids = [u.id_ for u in urls]

    # existing logic — do not remove
    total_links = len(urls)

    if not url_ids:
        total_clicks = 0
        clicks_today = 0
    else:
        total_clicks = UrlAnalytics.query.filter(
            UrlAnalytics.url_id.in_(url_ids)
        ).count()

        today = datetime.date.today()
        clicks_today = UrlAnalytics.query.filter(
            UrlAnalytics.url_id.in_(url_ids),
            cast(UrlAnalytics.timestamp, Date) == today
        ).count()

    # -----------------------------
    # NEW FIELDS (requested by you)
    # -----------------------------
    # Total short links (created through shortener or QR with show_short=True)
    total_short_links = Urls.query.filter_by(
        user_id=current_user.id,
        show_short=True
    ).count()

    # Total QRs (any URL that has qr_code stored)
    total_qrs = Urls.query.filter(
        Urls.user_id == current_user.id,
        Urls.qr_code.isnot(None)
    ).count()

    # -----------------------------
    # Return existing fields + new
    # -----------------------------
    return api_response(True, "Dashboard stats", {
        "user_id": current_user.id,
        "total_links": total_links,      # already present
        "total_clicks": total_clicks,    # already present
        "clicks_today": clicks_today,    # already present

        # NEW FIELDS
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

        base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")

        # ---------------------------------------------------------
        # CASE 1: URL HAS QR → REGENERATE QR + DELETE OLD QR FILE
        # ---------------------------------------------------------
        if url.qr_code:

            # ✔ Convert relative → absolute path
            old_qr_path = absolute_qr_path(url.qr_code)

            # ✔ Delete old QR
            if old_qr_path and os.path.exists(old_qr_path):
                try:
                    os.remove(old_qr_path)
                except Exception:
                    pass

            qr_data = f"{base_url}/{new_short}?source=qr"
            qr_dir = os.path.join(current_app.static_folder or "static", "qrcodes")
            os.makedirs(qr_dir, exist_ok=True)

            qr_filename = f"qr_{uuid.uuid4().hex}.png"
            qr_path = os.path.join(qr_dir, qr_filename)

            # === Restore QR style and colors ===
            color_dark = url.color_dark or "#000000"
            style = (url.style or "square").lower()

            try:
                fill_rgb = ImageColor.getrgb(color_dark)
            except Exception:
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
                color_mask=color_mask
            ).convert("RGB")

            # === Handle Logo ===
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
                    qr_width, qr_height = qr_img.size
                    logo_size = int(qr_width * 0.25)
                    logo = logo.resize((logo_size, logo_size))
                    pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                    qr_img.paste(logo, pos)

            except Exception as e:
                current_app.logger.warning(f"Logo embedding failed during edit: {e}")

            # ✔ Save new QR
            qr_img.save(qr_path)
            static_rel = os.path.relpath(qr_path, start=current_app.static_folder or "static").replace("\\", "/")

            # ✔ Update DB
            url.short = new_short
            url.qr_code = static_rel

            db.session.commit()

            return api_response(True, "Short URL updated successfully (QR regenerated)", {
                "newShortUrl": f"{base_url}/{new_short}",
                "newQrCode": build_static_url(static_rel)
            })

        # ---------------------------------------------------------
        # CASE 2: URL DID NOT HAVE QR → JUST UPDATE SHORT CODE
        # ---------------------------------------------------------
        else:
            url.short = new_short
            db.session.commit()

            return api_response(True, "Short URL updated successfully (no QR generated)", {
                "newShortUrl": f"{base_url}/{new_short}"
            })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Edit short URL error: {e}")
        return api_response(False, str(e), None)

 
 
 
@url_bp.route('/delete-account', methods=['DELETE'])
@token_required
def delete_account(current_user):
    try:
        # Step 1: Collect all URL IDs for this user
        url_ids = [u.id_ for u in Urls.query.with_entities(Urls.id_).filter_by(user_id=current_user.id).all()]
 
        if url_ids:
            # Step 2: Bulk delete all analytics for these URLs
            db.session.query(UrlAnalytics).filter(UrlAnalytics.url_id.in_(url_ids)).delete(synchronize_session=False)
 
            # Step 3: Delete QR code files in one go
            urls_with_qr = Urls.query.with_entities(Urls.qr_code).filter(Urls.id_.in_(url_ids)).all()
            for qr in urls_with_qr:
                if qr.qr_code and os.path.exists(qr.qr_code):
                    try:
                        os.remove(qr.qr_code)
                    except Exception as e:
                        current_app.logger.warning(f"QR deletion failed: {e}")
 
            # Step 4: Bulk delete all URLs of this user
            db.session.query(Urls).filter(Urls.id_.in_(url_ids)).delete(synchronize_session=False)
 
        # Step 5: Delete the user record
        db.session.delete(current_user)
 
        # Step 6: Commit once at the end
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
    ✅ Always generates a short URL for analytics tracking.
    ✅ If user selects only QR, the short link is hidden (show_short=False).
    ✅ QR encodes the short URL internally for accurate analytics.
    """
    import qrcode
    from PIL import Image, ImageColor
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import (
        SquareModuleDrawer, GappedSquareModuleDrawer,
        CircleModuleDrawer, RoundedModuleDrawer,
    )
    from qrcode.image.styles.colormasks import SolidFillColorMask
    from urllib.parse import urlparse
    import uuid, os, base64, io
 
    data = request.get_json(silent=True) or {}
 
    long_url = (data.get("long_url") or "").strip()
    show_short = bool(data.get("generate_short", False))  # user decides visibility
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
 
    base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")
 
    # === Handle short code logic ===
    if custom_short:
        if not custom_short.isalnum():
            return api_response(False, "Custom short URL must be alphanumeric.", None)
        existing = Urls.query.filter_by(short=custom_short).first()
        if existing:
            return api_response(False, "This custom short URL is already taken.", None)
        short_code = custom_short
    else:
        short_code = _shorten_url()
 
    # === QR should encode the short link (for analytics) ===
    qr_data = f"{base_url}/{short_code}?source=qr"
 
    # === QR code generation ===
    qr_dir = os.path.join(current_app.static_folder or "static", "qrcodes")
    os.makedirs(qr_dir, exist_ok=True)
    qr_filename = f"qr_{uuid.uuid4().hex}.png"
    qr_path = os.path.join(qr_dir, qr_filename)
 
    try:
        fill_rgb = ImageColor.getrgb(color_dark)
    except Exception:
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
        color_mask=color_mask
    ).convert("RGB")
 
    # ✅ Optional logo overlay
    if logo_data:
        try:
            if "," in logo_data:
                logo_data = logo_data.split(",", 1)[1]
            logo_bytes = base64.b64decode(logo_data)
            logo = Image.open(io.BytesIO(logo_bytes))
            qr_width, qr_height = qr_img.size
            logo_size = int(qr_width * 0.25)
            logo = logo.resize((logo_size, logo_size))
            pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
            qr_img.paste(logo, pos)
        except Exception as e:
            current_app.logger.warning(f"Logo embedding failed: {e}")
 
    qr_img.save(qr_path)
    static_rel = os.path.relpath(qr_path, start=current_app.static_folder or "static").replace("\\", "/")
 
    # === Save to DB ===
    new_url = Urls(
    long=long_url,
    short=short_code,
    user_id=current_user.id,
    qr_code=static_rel,
    show_short=show_short,
    color_dark=color_dark,
    style=style,
    logo=logo_data,
    title=title 
    )
 
    db.session.add(new_url)
    db.session.commit()
 
    # === Build response ===
    response_data = {
        "title": title,
        "long_url": long_url,
        "qr_code": build_static_url(static_rel),
        "created_at": new_url.created_at.isoformat(),
        "show_short": show_short,
    }
 
    if show_short:
        response_data["short_url"] = f"{base_url}/{short_code}"
 
    return api_response(True, "QR code generated successfully.", response_data)
 
 
 
 

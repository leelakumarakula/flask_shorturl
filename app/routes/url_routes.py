import os
import random
import string
import uuid
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

def get_country_from_ip(ip: str | None) -> str:
    ip = ip or ""
    try:
        res = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        if res.status_code == 200:
            data = res.json()
            return data.get("country_name", "Unknown")
    except Exception as e:
        logging.error(f"GeoIP lookup failed: {e}")
    return "Unknown"

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


@url_bp.route('/create', methods=['POST'])
@token_required
def create(current_user):
    data = request.get_json()
    if not data or "long_url" not in data:
        return api_response(False, "long_url is required", None)

    url_received = data.get("long_url", "").strip()
    if not url_received:
        return api_response(False, "long_url cannot be empty", None)

    parsed = urlparse(url_received)
    if not parsed.scheme:
        url_received = "https://" + url_received

    custom_short = data.get("custom", "").strip()
    if custom_short:
        if not custom_short.isalnum():
            return api_response(False, "Custom short URL must be alphanumeric.", None)
        existing_short = Urls.query.filter_by(short=custom_short).first()
        if existing_short:
            return api_response(False, "This custom short URL is already taken.", None)
        short_url = custom_short
    else:
        short_url = _shorten_url()

    qr_path = None
    if data.get("generate_qr"):
        qr_path = _generate_qr_code(short_url)

    new_url = Urls(long=url_received, short=short_url, user_id=current_user.id, qr_code=qr_path)
    db.session.add(new_url)
    db.session.commit()

    base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")
    qr_url = build_static_url(qr_path)
    return api_response(True, "New short URL created successfully.", {
        "short_url": f"{base_url}/{short_url}",
        "long_url": url_received,
        "qr_code": qr_url,
        "user_id": current_user.id,
        "created_at": new_url.created_at.isoformat()
    })


@url_bp.route('/<short_url>')
def redirection(short_url):
    url_entry = Urls.query.filter_by(short=short_url).first()
    if not url_entry:
        return api_response(False, "URL does not exist", None)

    # Parse user-agent
    user_agent_str = request.headers.get('User-Agent', "Unknown")
    ua = parse(user_agent_str)

    browser = ua.browser.family or "Unknown"
    browser_version = ua.browser.version_string or "Unknown"
    os_family = ua.os.family or "Unknown"
    os_version = ua.os.version_string or ""
    platform = f"{os_family} {os_version}".strip()

    # Get real client IP
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        ip_address = xff.split(',')[0].strip()
    else:
        ip_address = request.remote_addr or "0.0.0.0"

    country = get_country_from_ip(ip_address) if ip_address else "Unknown"

    # Skip analytics if browser or platform is "Other"
    if browser.lower() != "other" and os_family.lower() != "other":
        try:
            analytics = UrlAnalytics(
                url_id=url_entry.id_,
                user_agent=user_agent_str,
                browser=browser,
                browser_version=browser_version,
                platform=platform,
                os=os_family,
                ip_address=ip_address,
                country=country
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
    return api_response(True, "Analytics fetched", {
        "short_url": url_entry.short,
        "long_url": url_entry.long,
        "created_at": url_entry.created_at.isoformat(),
        "total_clicks": len(clicks),
        "clicks": [
            {
                "timestamp": c.timestamp.isoformat(),
                "ip_address": c.ip_address,
                "browser": c.browser,
                "browser_version": c.browser_version,
                "platform": c.platform,
                "os": c.os,
                "country": c.country
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
                "shorturl": f"{base_url}/{u.short}",
                "shortcode": u.short,
                "long": u.long,
                "created_at": u.created_at.isoformat(),
                "qr_code": build_static_url(u.qr_code),
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
    if url_entry.qr_code and os.path.exists(url_entry.qr_code):
        os.remove(url_entry.qr_code)
    UrlAnalytics.query.filter_by(url_id=url_entry.id_).delete()
    db.session.delete(url_entry)
    db.session.commit()

    return api_response(True, f"Short URL '{short_url}' deleted successfully.", None)


@url_bp.route('/totalclicks', methods=['GET'])
@token_required
def dashboard_stats(current_user):
    total_links = Urls.query.filter_by(user_id=current_user.id).count()
    user_urls = Urls.query.filter_by(user_id=current_user.id).all()
    url_ids = [u.id_ for u in user_urls]

    if not url_ids:
        total_clicks = 0
        from datetime import date as _date
        clicks_today = 0
    else:
        total_clicks = UrlAnalytics.query.filter(UrlAnalytics.url_id.in_(url_ids)).count()

        from datetime import date as _date
        today = _date.today()
        clicks_today = UrlAnalytics.query.filter(
            UrlAnalytics.url_id.in_(url_ids),
            cast(UrlAnalytics.timestamp, Date) == today
        ).count()

    return api_response(True, "Dashboard stats", {
        "user_id": current_user.id,
        "total_links": total_links,
        "total_clicks": total_clicks,
        "clicks_today": clicks_today
    })


@url_bp.route('/url/<short_url>', methods=['GET'])
@token_required
def get_url_details(current_user, short_url):
    url_entry = Urls.query.filter_by(short=short_url, user_id=current_user.id).first()
    if not url_entry:
        return api_response(False, "URL not found", None)

    return api_response(True, "URL details", {
        "short_url": url_entry.short,
        "long_url": url_entry.long,
        "qr_code": url_entry.qr_code,
        "created_at": url_entry.created_at.isoformat()
    })


@url_bp.route('/edit', methods=['PUT'])
@token_required
def edit_short_url(current_user):
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
        if url.qr_code!=None:
            if url.qr_code and os.path.exists(url.qr_code):
                try:
                    os.remove(url.qr_code)
                except Exception:
                    pass

            url.short = new_short
            url.qr_code = _generate_qr_code(new_short)
            db.session.commit()
        else:
            url.short=new_short
            db.session.commit()

        base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")
        qr_url = build_static_url(url.qr_code)
        return api_response(True, "Short URL updated successfully", {
            "newShortUrl": f"{base_url}/{new_short}",
            "newQrCode": qr_url
        })

    except Exception as e:
        db.session.rollback()
        return api_response(False, str(e), None)



import logging
import datetime
import random
import string
import requests
from functools import wraps
from urllib.parse import urlparse
from datetime import date
from flask import Flask, request, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import jwt
from datetime import timezone
# User-Agent parser
from user_agents import parse
from werkzeug.middleware.proxy_fix import ProxyFix
import qrcode
import os

# ----------------- APP CONFIG -----------------
app = Flask(__name__)
CORS(app)
app.secret_key = "8y56jJ3YQwGh4QvNf/saEgyrGw2FjHzsQV5n+6k6Skw=abcdefghijk=/568390ogsariblmnrdig"  # use env var in prod
app.config['SQLALCHEMY_DATABASE_URI'] = 'mssql+pymssql://vinodh:Ethically7-Jurist-Rumb33w@10.100.0.37/SHORTURL'


 
 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
  
# Proxy fix for correct client IP
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
 
# ----------------- MODELS -----------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    firstname = db.Column(db.String(100), nullable=False)
    lastname = db.Column(db.String(100), nullable=False)
    organization = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
 
    client_id = db.Column(db.String(100), unique=True)
    client_secret = db.Column(db.String(200))
 
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


 
class Urls(db.Model):
    __tablename__ = "urls"
    id_ = db.Column("id_", db.Integer, primary_key=True)
    long = db.Column("long", db.String())
    short = db.Column("short", db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    qr_code = db.Column(db.String(255), unique=True)   # ✅ fixed
    user = db.relationship("User", backref=db.backref("urls", lazy=True))
 
class UrlAnalytics(db.Model):
    __tablename__ = "url_analytics"
    id = db.Column(db.Integer, primary_key=True)
    url_id = db.Column(db.Integer, db.ForeignKey('urls.id_'), nullable=False)
    user_agent = db.Column(db.String(300))
    browser = db.Column(db.String(100))
    browser_version = db.Column(db.String(50))
    platform = db.Column(db.String(100))   # OS + version
    os = db.Column(db.String(50))          # OS family
    ip_address = db.Column(db.String(50))
    country = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
 
    url = db.relationship("Urls", backref=db.backref("analytics", lazy=True))
 
with app.app_context():
    db.create_all()

# ----------------- HELPERS -----------------
def shorten_url():
    chars = string.ascii_letters + string.digits
    while True:
        rand_chars = ''.join(random.choices(chars, k=7))
        short_url = Urls.query.filter_by(short=rand_chars).first()
        if not short_url:
            return rand_chars

from PIL import Image
import qrcode
import uuid
import os

def generate_qr_code(short_code):
    qr_dir = "static/qrcodes"
    os.makedirs(qr_dir, exist_ok=True)

    short_url_full = f"http://127.0.0.1:5000/{short_code}"

    # Unique filename
    qr_filename = f"{short_code}_{uuid.uuid4().hex}.png"
    qr_path = os.path.join(qr_dir, qr_filename)

    # Step 1: Create QR code with error correction
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High for logo overlay
        box_size=10,
        border=4,
    )
    qr.add_data(short_url_full)
    qr.make(fit=True)

    # Step 2: Generate QR image
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Step 3: Load your logo
    logo_path = "static/image.png"  # <-- your logo
    if os.path.exists(logo_path):
        logo = Image.open(logo_path)

        # Resize logo (20–25% of QR size)
        qr_width, qr_height = qr_img.size
        logo_size = int(qr_width * 0.25)
        logo = logo.resize((logo_size, logo_size))

        # ✅ Add padding around logo
        padding = 10  # pixels
        padded_size = (logo_size + padding * 2, logo_size + padding * 2)

        # Create white box for padding (use "RGBA" if you want transparency instead of white)
        padded_logo = Image.new("RGB", padded_size, "white")
        padded_logo.paste(logo, (padding, padding), mask=logo if logo.mode == "RGBA" else None)

        # Step 4: Paste padded logo in center
        pos = ((qr_width - padded_size[0]) // 2, (qr_height - padded_size[1]) // 2)
        qr_img.paste(padded_logo, pos)

    # Step 5: Save final QR
    qr_img.save(qr_path)

    return qr_path





def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if " " in auth_header:
                token = auth_header.split(" ")[1]  # Bearer <token>
            else:
                token = auth_header

        if not token: 
            return jsonify({"success": False, "message": "Token is missing!"}), 401

        try:
            payload = jwt.decode(token, app.secret_key, algorithms=["HS256"])
            current_user = User.query.get(payload['user_id'])
            if not current_user:
                return jsonify({"success": False, "message": "User not found!"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "message": "Token has expired!"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "message": "Invalid token!"}), 401

        return f(current_user, *args, **kwargs)
    return decorated
 
def get_country_from_ip(ip):
    try:
        res = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3)
        if res.status_code == 200:
            data = res.json()
            return data.get("country_name", "Unknown")
    except Exception as e:
        logging.error(f"GeoIP lookup failed: {e}")
    return "Unknown"
 
# ----------------- ROUTES -----------------
@app.route('/')
def root():
    return jsonify({"message": "Welcome to API. Use Angular frontend for UI."})

import secrets

@app.route('/signups', methods=['POST'])
def signup():
    data = request.get_json()
 
    firstname = data.get('firstname')
    lastname = data.get('lastname')
    organization = data.get('organization')
    phone = data.get('phone')
    email = data.get('email')
    password = generate_password_hash(data.get('password'))
 
    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"success": False, "message": "User already exists"}), 200
 
    client_id = secrets.token_hex(8)      
    raw_secret = secrets.token_hex(16)    
 
    new_user = User(
        firstname=firstname,
        lastname=lastname,
        organization=organization,
        phone=phone,
        email=email,
        password=password,
        client_id=client_id,
        client_secret=raw_secret
    )
 
    db.session.add(new_user)
    db.session.commit()
 
    # Issue JWT for convenience
    token = jwt.encode(
    {
        "user_id": new_user.id,  
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    },
    app.secret_key,
    algorithm="HS256"
)
 
 
    return jsonify({
    "success": True,
    "message": "Signup successful",
    "token": token,
    "client_id": client_id,
    "client_secret": raw_secret  
}), 201

@app.route('/token', methods=['POST'])
def get_token():
    data = request.get_json()
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
 
    if not client_id or not client_secret:
        return jsonify({"success": False, "message": "Missing credentials"}), 400
 
    user = User.query.filter_by(client_id=client_id).first()
    if not user:
        return jsonify({"success": False, "message": "Invalid client_id"}), 401
 
    token = jwt.encode(
    {
        "user_id": user.id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    },
    app.secret_key,
    algorithm="HS256"
)
 
 
    return jsonify({"success": True, "access_token": token}), 200
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"success": False, "message": "Account does not exist. Please sign up first."}), 404
    if check_password_hash(user.password, password):
        token = jwt.encode(
            {"user_id": user.id,
             "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
            app.secret_key,
            algorithm="HS256"
        )
        return jsonify({"success": True, "token": token}), 200
 
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route('/home')
@token_required
def home(current_user):
    return jsonify({"success": True, "message": f"Welcome Home {current_user.firstname}"})

@app.route('/create', methods=['POST'])
@token_required
def create(current_user):
    data = request.get_json()
    if not data or "long_url" not in data:
        return jsonify({"success": False, "message": "long_url is required"}), 400

    url_received = data.get("long_url", "").strip()
    if not url_received:
        return jsonify({"success": False, "message": "long_url cannot be empty"}), 400

    parsed = urlparse(url_received)
    if not parsed.scheme:
        url_received = "https://" + url_received

    custom_short = data.get("custom", "").strip()
    if custom_short:
        if not custom_short.isalnum():
            return jsonify({"message": "Custom short URL must be alphanumeric."}), 400
        existing_short = Urls.query.filter_by(short=custom_short).first()
        if existing_short:
            return jsonify({"message": "This custom short URL is already taken."}), 400
        short_url = custom_short
    else:
        short_url = shorten_url()

    # ✅ Generate QR Code for this short URL
    qr_path = None
    if data.get("generate_qr"):
        qr_path = generate_qr_code(short_url)

    new_url = Urls(long=url_received, short=short_url, user_id=current_user.id, qr_code=qr_path)
    db.session.add(new_url)
    db.session.commit()

    return jsonify({
        "short_url": short_url,
        "long_url": url_received,
        "qr_code": qr_path,   # return QR file path
        "user_id": current_user.id,
        "created_at": new_url.created_at.isoformat(),
        "message": "New short URL created successfully."
    }), 201

 
@app.route('/<short_url>')
def redirection(short_url):
    url_entry = Urls.query.filter_by(short=short_url).first()
    if not url_entry:
        return "<h1>URL does not exist</h1>", 404
 
    user_agent_str = request.headers.get('User-Agent', "Unknown")
    ua = parse(user_agent_str)
 
    browser = ua.browser.family or "Unknown"
    browser_version = ua.browser.version_string or "Unknown"
    os_family = ua.os.family or "Unknown"
    os_version = ua.os.version_string or ""
    platform = f"{os_family} {os_version}".strip()
 
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        ip_address = xff.split(',')[0].strip()
    else:
        ip_address = request.remote_addr or "0.0.0.0"
 
    country = "Unknown"  # placeholder for future GeoIP enrichment
 
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
    except Exception as e:
        db.session.rollback()
        logging.error(f"Analytics save failed: {e}")
 
    return redirect(url_entry.long, code=302)
 
@app.route('/analytics/<short_url>')
@token_required
def get_analytics(current_user, short_url):
    url_entry = Urls.query.filter_by(short=short_url, user_id=current_user.id).first()
    if not url_entry:
        return jsonify({"error": "URL not found or not yours"}), 404
 
    clicks = UrlAnalytics.query.filter_by(url_id=url_entry.id_).order_by(UrlAnalytics.timestamp.desc()).all()
    return jsonify({
        "short_url": url_entry.short,
        "long_url": url_entry.long,
        "created_at": url_entry.created_at.isoformat(),  # ← include date
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
 
@app.route('/userinfo', methods=['GET'])
@token_required
def display_user_info(current_user):
    return jsonify({
        "success": True,
        "user": {
            "id": current_user.id,
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "email": current_user.email,
            "organization": current_user.organization,
            "phone": current_user.phone,
            "client_id": current_user.client_id,
            "client_secret": current_user.client_secret,
            "created_at": current_user.created_at.isoformat()
        }
    }), 200

@app.route('/myurls', methods=['GET'])
@token_required
def my_urls(current_user):
    urls = Urls.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        "success": True,
        "user_id": current_user.id,
        "urls": [
            {
                "short": u.short,
                "long": u.long,
                "created_at": u.created_at.isoformat(),
                "qr_code": u.qr_code  # ✅ send QR code path
            }
            for u in urls
        ]
    })


@app.route('/urlcount', methods=['GET'])
@token_required
def url_count(current_user):
    count = Urls.query.filter_by(user_id=current_user.id).count()
    return jsonify({
        "success": True,
        "user_id": current_user.id,
        "total_urls": count
    })


@app.route('/delete/<short_url>', methods=['DELETE'])
@token_required
def delete_url(current_user, short_url):
    url_entry = Urls.query.filter_by(short=short_url, user_id=current_user.id).first()
    if not url_entry:
        return jsonify({"success": False, "message": "URL not found or you don't have permission to delete"}), 404
    #delete the respected qr code file if exists
    if url_entry.qr_code and os.path.exists(url_entry.qr_code):
        os.remove(url_entry.qr_code)
    UrlAnalytics.query.filter_by(url_id=url_entry.id_).delete()
    db.session.delete(url_entry)
    db.session.commit()
 
    return jsonify({
        "success": True,
        "message": f"Short URL '{short_url}' deleted successfully."
    }), 200
 
@app.route('/totalclicks', methods=['GET'])
@token_required
def dashboard_stats(current_user):
    # Total Links
    total_links = Urls.query.filter_by(user_id=current_user.id).count()
 
    # All URLs for this user
    user_urls = Urls.query.filter_by(user_id=current_user.id).all()
    url_ids = [u.id_ for u in user_urls]
 
    # Total Clicks for all URLs
    total_clicks = UrlAnalytics.query.filter(UrlAnalytics.url_id.in_(url_ids)).count()
 
    # Clicks Today
    today = date.today()
    clicks_today = UrlAnalytics.query.filter(
        UrlAnalytics.url_id.in_(url_ids),
        db.func.date(UrlAnalytics.timestamp) == today
    ).count()
 
    return jsonify({
        "success": True,
        "user_id": current_user.id,
        "total_links": total_links,
        "total_clicks": total_clicks,
        "clicks_today": clicks_today
    })
 

 
@app.route('/url/<short_url>', methods=['GET'])
@token_required
def get_url_details(current_user, short_url):
    url_entry = Urls.query.filter_by(short=short_url, user_id=current_user.id).first()
    if not url_entry:
        return jsonify({"success": False, "message": "URL not found"}), 404

    return jsonify({
        "success": True,
        "short_url": url_entry.short,
        "long_url": url_entry.long,
        "qr_code": url_entry.qr_code,  # <-- QR path
        "created_at": url_entry.created_at.isoformat()
    })

@app.route('/edit', methods=['PUT'])
@token_required
def edit_short_url(current_user):
    try:
        data = request.get_json()
        old_short = data.get("old_short")
        new_short = data.get("new_short")
 
        # validation
        if not old_short or not new_short:
            return jsonify({"success": False, "message": "Missing fields"}), 400
        if not new_short.isalnum():
            return jsonify({"success": False, "message": "Short code must be alphanumeric"}), 400
        if Urls.query.filter_by(short=new_short).first():
            return jsonify({"success": False, "message": "Short URL already exists"}), 400
 
        url = Urls.query.filter_by(short=old_short, user_id=current_user.id).first()
        if not url:
            return jsonify({"success": False, "message": "Old short URL not found"}), 404
 
        # remove old QR code if exists
        if url.qr_code and os.path.exists(url.qr_code):
            try:
                os.remove(url.qr_code)
            except Exception as e:
                logging.warning(f"Failed to remove old QR file: {e}")
 
        # update short and regenerate QR code
        url.short = new_short
        url.qr_code = generate_qr_code(new_short)  # generate_qr_code should return path/filename
 
        db.session.commit()
 
        return jsonify({
            "success": True,
            "message": "Short URL updated successfully",
            "newShortUrl": new_short,
            "newQrCode": url.qr_code   # important: return new QR code path
        }), 200
 
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error in edit_short_url: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get("email")

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"success": False, "message": "Email not registered"}), 404

    return jsonify({"success": True, "message": "Email exists, proceed to reset"}), 200


@app.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    new_password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user.password = generate_password_hash(new_password)
    db.session.commit()

    return jsonify({"success": True, "message": "Password updated successfully"}), 200



 
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


import secrets
from flask import Blueprint, request
from werkzeug.security import generate_password_hash
from app.extensions import db

# from ..extensions import db
from ..models.user import User
from ..utils.jwt_helper import encode_token, decode_token
from ..utils.response import api_response
from ..utils.passwords import verify_and_upgrade_password


auth_bp = Blueprint("auth", __name__)


@auth_bp.route('/signups', methods=['POST'])
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
        return api_response(False, "User already exists", None)

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

    token = encode_token(new_user.id)

    return api_response(True, "Signup successful", {
        "token": token,
        "client_id": client_id,
        "client_secret": raw_secret
    })


@auth_bp.route('/token', methods=['POST'])
def get_token():
    data = request.get_json()
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")

    if not client_id or not client_secret:
        return api_response(False, "Missing credentials", None)

    user = User.query.filter_by(client_id=client_id).first()
    if not user:
        return api_response(False, "Invalid client_id", None)

    token = encode_token(user.id)

    return api_response(True, "Token issued", {"access_token": token})


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user:
        return api_response(False, "Account does not exist. Please sign up first.", None)
    is_valid, new_hash = verify_and_upgrade_password(user.password, password)
    if is_valid:
        if new_hash:
            user.password = new_hash
            db.session.commit()
        token = encode_token(user.id)
        return api_response(True, "Login successful", {"token": token})

    return api_response(False, "Invalid credentials", None)


def token_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if " " in auth_header:
                token = auth_header.split(" ")[1]
            else:
                token = auth_header

        if not token:
            return api_response(False, "Token is missing!", None)

        try:
            payload = decode_token(token)
            current_user = User.query.get(payload['user_id'])
            if not current_user:
                return api_response(False, "User not found!", None)
        except Exception:
            return api_response(False, "Invalid or expired token!", None)

        return f(current_user, *args, **kwargs)

    return decorated


@auth_bp.route('/home')
@token_required
def home(current_user):
    return api_response(True, f"Welcome Home {current_user.firstname}", None)



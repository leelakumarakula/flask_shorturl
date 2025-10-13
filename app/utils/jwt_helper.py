import datetime
import jwt
from flask import current_app


def encode_token(user_id: int, hours: int = 1) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=hours),
    }
    token = jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")
    return token


def decode_token(token: str) -> dict:
    payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    return payload



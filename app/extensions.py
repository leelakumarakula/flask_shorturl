# app/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import redis

db = SQLAlchemy()
cors = CORS()
redis_client = None


def init_redis(app):
    """Initialize Redis using REDIS_URL from config."""
    global redis_client

    url = app.config.get("REDIS_URL")
    print(">>> init_redis() called")

    if not url:
        print(">>> No REDIS_URL found in environment")
        redis_client = None
        return

    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        redis_client = client
        print(">>> Redis OK — connected successfully")
        app.logger.info("Redis initialized successfully.")
    except Exception as exc:
        redis_client = None
        print(">>> Redis ERROR:", exc)
        app.logger.warning(f"Redis initialization failed: {exc}")

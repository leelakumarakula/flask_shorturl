# import os
# from dotenv import load_dotenv

# load_dotenv()


# def _require_env(key: str) -> str:
#     value = os.getenv(key)
#     if not value:
#         raise RuntimeError(f"Missing required environment variable: {key}")
#     return value


# class Config:
#     SECRET_KEY = _require_env("SECRET_KEY")
#     SQLALCHEMY_DATABASE_URI = _require_env("DATABASE_URL")
#     BASE_URL = _require_env("BASE_URL")
#     SQLALCHEMY_TRACK_MODIFICATIONS = False


import os
from dotenv import load_dotenv
 
load_dotenv()
 
def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value
 
class Config:
    SECRET_KEY = _require_env("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _require_env("DATABASE_URL")
    BASE_URL = _require_env("BASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
 
    REDIS_URL = os.getenv("REDIS_URL")
    REDIS_TTL = int(os.getenv("REDIS_TTL", 3600))

    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")
 
    if not REDIS_URL:
        REDIS_URL = "redis://localhost:6379/0"
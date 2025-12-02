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
#     # Redis configuration (optional — sensible defaults provided)
#     REDIS_URL = os.getenv("REDIS_URL")
#     REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
#     REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
#     REDIS_DB = int(os.getenv("REDIS_DB", 0))
#     # TTL (seconds) for cached short -> long mapping
#     REDIS_TTL = int(os.getenv("REDIS_TTL", 3600))
#     # If REDIS_URL not set, build one from individual parts
#     if not REDIS_URL:
#         REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"


import os
from dotenv import load_dotenv

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

    if not REDIS_URL:
        REDIS_URL = "redis://localhost:6379/0"

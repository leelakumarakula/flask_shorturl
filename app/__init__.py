import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import db, cors
from .utils.error_handler import register_error_handlers
from .routes.auth_routes import auth_bp
from .routes.core_routes import core_bp
from .routes.url_routes import url_bp


def create_app() -> Flask:
    # Serve static from project-level /static
    app = Flask(__name__, static_folder="../static", static_url_path="/static")

    # Configuration
    app.config.from_object(Config)

    # Extensions
    cors.init_app(app)
    db.init_app(app)

    # Proxy fix for correct client IPs behind proxies
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # Blueprints
    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp, url_prefix="/")
    app.register_blueprint(url_bp, url_prefix="/")

    # Error handlers
    register_error_handlers(app)

    # Ensure DB tables exist (simple setup; use migrations in prod)
    with app.app_context():
        from .models.user import User  # noqa: F401
        from .models.url import Urls  # noqa: F401
        from .models.url_analytics import UrlAnalytics  # noqa: F401
        db.create_all()

    return app



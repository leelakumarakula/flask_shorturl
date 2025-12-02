# app/__init__.py

import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config
from app.extensions import db, cors, init_redis
from app.utils.error_handler import register_error_handlers
from app.routes.auth_routes import auth_bp
from app.routes.core_routes import core_bp
from app.routes.url_routes import url_bp

# ⭐ ADD THIS IMPORT
from app.routes.subscription_routes import subscription_bp


# app/__init__.py
 
import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
 
from app.config import Config
from app.extensions import db, cors, init_redis
from app.utils.error_handler import register_error_handlers
from app.routes.auth_routes import auth_bp
from app.routes.core_routes import core_bp
from app.routes.url_routes import url_bp
 
 
def create_app() -> Flask:
    app = Flask(__name__, static_folder="../static", static_url_path="/static")

    # Load configuration
    app.config.from_object(Config)

    # Initialize extensions
    cors.init_app(app)
    db.init_app(app)

    # Initialize Redis
    try:
        init_redis(app)
        import app.extensions as extensions
        print(">>> Redis initialized in create_app:", extensions.redis_client)
    except Exception as e:
        print(">>> Redis init error:", e)

    # Fix proxy headers
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # Register blueprints
    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp, url_prefix="/")
    app.register_blueprint(url_bp, url_prefix="/")

    # ⭐ REGISTER SUBSCRIPTION ROUTES HERE
    app.register_blueprint(subscription_bp, url_prefix="/subscription")

    # Create tables if not exists
    with app.app_context():
        from app.models.user import User
        from app.models.url import Urls
        from app.models.url_analytics import UrlAnalytics
        db.create_all()
        # Ensure `edit_count` column exists on users table (handle older DBs)
        try:
            from sqlalchemy import inspect, text

            insp = inspect(db.engine)
            cols = [c['name'] for c in insp.get_columns('users')]
            if 'edit_count' not in cols:
                # Add column in a DB-agnostic way where possible
                dialect = db.engine.dialect.name
                if dialect == 'sqlite':
                    db.engine.execute(text('ALTER TABLE users ADD COLUMN edit_count INTEGER DEFAULT 0'))
                else:
                    # For postgres/mysql, add column with default 0
                    db.engine.execute(text('ALTER TABLE users ADD COLUMN edit_count INTEGER DEFAULT 0'))
        except Exception as e:
            app.logger.warning(f"Could not ensure edit_count column exists: {e}")

    return app

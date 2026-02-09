# import os
# from flask import Flask
# from werkzeug.middleware.proxy_fix import ProxyFix

# from .config import Config
# from .extensions import db, cors
# from .utils.error_handler import register_error_handlers
# from .routes.auth_routes import auth_bp
# from .routes.core_routes import core_bp
# from .routes.url_routes import url_bp


# def create_app() -> Flask:
#     # Serve static from project-level /static
#     app = Flask(__name__, static_folder="../static", static_url_path="/static")

#     # Configuration
#     app.config.from_object(Config)

#     # Extensions
#     cors.init_app(app)
#     db.init_app(app)

#     # Proxy fix for correct client IPs behind proxies
#     app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

#     # Blueprints
#     app.register_blueprint(core_bp)
#     app.register_blueprint(auth_bp, url_prefix="/")
#     app.register_blueprint(url_bp, url_prefix="/")

#     # Error handlers
#     register_error_handlers(app)

#     # Ensure DB tables exist (simple setup; use migrations in prod)
#     with app.app_context():
#         from .models.user import User  # noqa: F401
#         from .models.url import Urls  # noqa: F401
#         from .models.url_analytics import UrlAnalytics  # noqa: F401
#         db.create_all()

#     return app


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
        # import extensions module to read the live redis_client value
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
    
    from app.routes.subscription_routes import subscription_bp
    app.register_blueprint(subscription_bp, url_prefix="/api/subscription")
    
    from app.routes.webhook_routes import webhook_bp
    app.register_blueprint(webhook_bp, url_prefix="/api/subscription")
 
    # Create tables if not exists
    with app.app_context():
        from app.models.plan import Plan
        from app.models.user import User
        from app.models.url import Urls
        from app.models.url_analytics import UrlAnalytics
        from app.models.subscription import RazorpaySubscriptionPlan, Subscription
        from app.models.billing_info import BillingInfo
        from app.models.webhook_events import WebhookEvent
        from app.models.subscription_history import SubscriptionHistory
        db.create_all()
 
    return app
 
 

 
 
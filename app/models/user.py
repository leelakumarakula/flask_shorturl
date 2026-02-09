import datetime
from ..extensions import db
 
 
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
 
    # Consumption Counters (Lifetime usage)
    usage_links = db.Column(db.Integer, default=0, nullable=False)
    usage_qrs = db.Column(db.Integer, default=0, nullable=False)
    usage_qr_with_logo = db.Column(db.Integer, default=0, nullable=False)
    usage_editable_links = db.Column(db.Integer, default=0, nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=True)
    plan = db.relationship("Plan", backref=db.backref("users", lazy=True))
 
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
   
    # Custom Limits (JSON) - Overrides Plan Limits
    custom_limits = db.Column(db.Text, nullable=True)
    permanent_custom_limits = db.Column(db.Boolean, default=False, nullable=False)
 
    def get_limit(self, limit_name):
        """
        Get the effective limit for a feature.
        Priority: User Custom Limit > Plan Limit
        """
        import json
       
        # 1. Check Custom Limits
        if self.custom_limits:
            try:
                limits = json.loads(self.custom_limits)
                if limit_name in limits:
                    return limits[limit_name]
            except:
                pass # Invalid JSON, ignore
       
        # 2. Check Plan Limits
        if self.plan:
             return getattr(self.plan, limit_name, 0)
             
        # 3. Default (No Plan)
        return 0
 
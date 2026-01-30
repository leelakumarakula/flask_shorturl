import datetime
from ..extensions import db
 
 
class Urls(db.Model):
    __tablename__ = "urls"
 
    id_ = db.Column("id_", db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=True)  # Optional custom title
 
    long = db.Column("long", db.String())
    short = db.Column("short", db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    qr_code = db.Column(db.String(255), nullable=True)
    show_short = db.Column(db.Boolean, default=True)
    color_dark = db.Column(db.String(20))
    style = db.Column(db.String(50))
    logo = db.Column(db.Text)

    # Subscription tracking fields
    is_custom = db.Column(db.Boolean, default=False)
    is_edited = db.Column(db.Boolean, default=False)
    plan_name = db.Column(db.String(50), nullable=True)
 
 
 
    user = db.relationship("User", backref=db.backref("urls", lazy=True))
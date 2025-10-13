import datetime
from ..extensions import db


class UrlAnalytics(db.Model):
    __tablename__ = "url_analytics"

    id = db.Column(db.Integer, primary_key=True)
    url_id = db.Column(db.Integer, db.ForeignKey('urls.id_'), nullable=False)
    user_agent = db.Column(db.String(300))
    browser = db.Column(db.String(100))
    browser_version = db.Column(db.String(50))
    platform = db.Column(db.String(100))
    os = db.Column(db.String(50))
    ip_address = db.Column(db.String(50))
    country = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    url = db.relationship("Urls", backref=db.backref("analytics", lazy=True))



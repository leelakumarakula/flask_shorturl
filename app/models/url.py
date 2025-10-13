import datetime
from ..extensions import db


class Urls(db.Model):
    __tablename__ = "urls"

    id_ = db.Column("id_", db.Integer, primary_key=True)
    long = db.Column("long", db.String())
    short = db.Column("short", db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    qr_code = db.Column(db.String(255), unique=True)

    user = db.relationship("User", backref=db.backref("urls", lazy=True))



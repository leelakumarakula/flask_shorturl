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

    plan = db.Column(db.String(50), default="free")  
    plan_expires = db.Column(db.DateTime, nullable=True)  
    edit_count = db.Column(db.Integer, default=0)


    total_links_created = db.Column(db.Integer, default=0)
    total_qr_created = db.Column(db.Integer, default=0)
    total_custom_created = db.Column(db.Integer, default=0)


 
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
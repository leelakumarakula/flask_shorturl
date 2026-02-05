import datetime
from app.extensions import db

class BillingInfo(db.Model):
    __tablename__ = 'billing_info'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=True)
    
    razorpay_plan_id = db.Column(db.String(255), nullable=True)
    razorpay_plan_id = db.Column(db.String(255), nullable=True)
    razorpay_subscription_id = db.Column(db.String(255), nullable=True)
    amount = db.Column(db.Float, default=0.0)
    plan_id = db.Column(db.Integer, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<BillingInfo {self.user_id} - {self.email}>"

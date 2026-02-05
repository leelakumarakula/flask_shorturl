import datetime
import uuid
from ..extensions import db

class RazorpaySubscriptionPlan(db.Model):
    __tablename__ = 'razorpay_subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    plan_name = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.String(36), default=lambda: str(uuid.UUID(int=0)), nullable=True)  # Guid?
    razorpay_plan_id = db.Column(db.String(255), nullable=True)
    period = db.Column(db.String(50), nullable=True)
    interval = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_date = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    is_renewal_plan = db.Column(db.Boolean, default=False)
    pro_rated_amount = db.Column(db.Float, default=0.0, nullable=True)

    def __repr__(self):
        return f"<RazorpaySubscriptionPlan {self.plan_name}>"


class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, default=0, nullable=True)
    cart_id = db.Column(db.String(255), default='', nullable=True)
    razorpay_plan_id = db.Column(db.String(255), default='', nullable=True)
    plan_amount = db.Column(db.Float, default=0.0, nullable=True)
    razorpay_subscription_id = db.Column(db.String(255), default='', nullable=True)
    razorpay_signature_id = db.Column(db.String(255), default='', nullable=True)
    subscription_status = db.Column(db.String(50), default='Pending', nullable=True)
    subscription_start_date = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    created_date = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=True)
    updated_date = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(50), default='', nullable=True)
    is_active = db.Column(db.Boolean, default=False, nullable=True)
    basic_plan_id = db.Column(db.Integer, default=0, nullable=True)
    next_billing_date = db.Column(db.DateTime, nullable=False)
    is_add_on = db.Column(db.Boolean, default=False, nullable=True)
    short_url = db.Column(db.String(255), default='', nullable=True)
    card_id = db.Column(db.String(255), default='', nullable=True)
    total_count = db.Column(db.Integer, default=12, nullable=True)
    customer_notify = db.Column(db.Boolean, default=True, nullable=True)
    start_at = db.Column(db.Integer, nullable=True) # Timestamp
    expire_by = db.Column(db.Integer, nullable=True) # Timestamp
    addons = db.Column(db.Text, nullable=True) # Storing JSON as Text
    offer_id = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True) # Storing JSON as Text

    def __repr__(self):
        return f"<Subscription {self.id}>"

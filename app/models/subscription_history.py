import datetime
import uuid
from ..extensions import db

class SubscriptionHistory(db.Model):
    __tablename__ = 'subscription_history'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id = db.Column(db.String(255), nullable=False)  # Razorpay subscription ID
    user_id = db.Column(db.Integer, nullable=False)
    razorpay_plan_id = db.Column(db.String(255), nullable=True)
    plan_amount = db.Column(db.Float, default=0.0, nullable=True)
    cancelled_date = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    cancelled_reason = db.Column(db.String(255), default='User Requested', nullable=True)
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Additional metadata
    card_id = db.Column(db.String(255), nullable=True)
    total_count = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<SubscriptionHistory {self.id}>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'subscription_id': self.subscription_id,
            'user_id': self.user_id,
            'razorpay_plan_id': self.razorpay_plan_id,
            'plan_amount': self.plan_amount,
            'cancelled_date': self.cancelled_date.isoformat() if self.cancelled_date else None,
            'cancelled_reason': self.cancelled_reason,
            'subscription_start_date': self.subscription_start_date.isoformat() if self.subscription_start_date else None,
            'subscription_end_date': self.subscription_end_date.isoformat() if self.subscription_end_date else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

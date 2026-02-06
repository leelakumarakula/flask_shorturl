import datetime
import uuid
from ..extensions import db


class WebhookEvent(db.Model):
    __tablename__ = 'webhook_events'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = db.Column(db.String(255), unique=True, nullable=False, index=True)  # Razorpay event ID for idempotency
    event_type = db.Column(db.String(100), nullable=False, index=True)  # e.g., payment.captured, subscription.activated
    payload = db.Column(db.Text, nullable=False)  # Complete JSON payload from Razorpay
    signature = db.Column(db.String(512), nullable=True)  # Webhook signature for audit
    processed = db.Column(db.Boolean, default=False, nullable=False, index=True)  # Processing status
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime, nullable=True)  # When the event was processed
    error_message = db.Column(db.Text, nullable=True)  # Any errors during processing
    
    # Additional metadata
    subscription_id = db.Column(db.String(255), nullable=True, index=True)  # Razorpay subscription ID
    payment_id = db.Column(db.String(255), nullable=True, index=True)  # Razorpay payment ID
    user_id = db.Column(db.Integer, nullable=True, index=True)  # User ID if identifiable

    def __repr__(self):
        return f"<WebhookEvent {self.event_id} - {self.event_type}>"

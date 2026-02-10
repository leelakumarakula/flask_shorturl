import datetime
import uuid
from ..extensions import db


class UserDeletionHistory(db.Model):
    """
    Stores historical data of deleted user accounts for audit and compliance purposes.
    This table persists even after user accounts are deleted.
    """
    __tablename__ = 'user_deletion_history'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # User Information
    user_id = db.Column(db.Integer, nullable=False, index=True)  # Original user ID (not a foreign key)
    firstname = db.Column(db.String(100), nullable=False)
    lastname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False)
    organization = db.Column(db.String(200), nullable=True)
    
    # Account Dates
    account_created_at = db.Column(db.DateTime, nullable=False)
    account_deleted_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    
    # Subscription Information (Latest/Last Active)
    last_subscription_plan = db.Column(db.String(100), nullable=True)  # Plan name (e.g., "Pro", "Premium")
    last_subscription_date = db.Column(db.DateTime, nullable=True)  # When the last subscription started
    last_subscription_end_date = db.Column(db.DateTime, nullable=True)  # When it ended/was cancelled
    last_subscription_amount = db.Column(db.Float, nullable=True)
    razorpay_subscription_id = db.Column(db.String(255), nullable=True)  # Last Razorpay subscription ID
    
    # Billing Information (Latest)
    billing_first_name = db.Column(db.String(100), nullable=True)
    billing_last_name = db.Column(db.String(100), nullable=True)
    billing_email = db.Column(db.String(120), nullable=True)
    billing_phone = db.Column(db.String(20), nullable=True)
    billing_address = db.Column(db.Text, nullable=True)
    
    # Usage Statistics (at time of deletion)
    total_links_created = db.Column(db.Integer, default=0)
    total_qrs_created = db.Column(db.Integer, default=0)
    total_clicks = db.Column(db.Integer, default=0)
    
    # Deletion Metadata
    deletion_reason = db.Column(db.String(255), nullable=True)  # Optional: why account was deleted
    deleted_by = db.Column(db.String(50), default='user', nullable=True)  # 'user', 'admin', 'system'
    ip_address = db.Column(db.String(50), nullable=True)  # IP from which deletion was requested
    
    # Additional metadata (JSON format for flexibility)
    additional_metadata = db.Column(db.Text, nullable=True)  # Store any additional info as JSON
    
    def __repr__(self):
        return f"<UserDeletionHistory {self.email} - Deleted on {self.account_deleted_at}>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'firstname': self.firstname,
            'lastname': self.lastname,
            'email': self.email,
            'phone': self.phone,
            'organization': self.organization,
            'account_created_at': self.account_created_at.isoformat() if self.account_created_at else None,
            'account_deleted_at': self.account_deleted_at.isoformat() if self.account_deleted_at else None,
            'last_subscription_plan': self.last_subscription_plan,
            'last_subscription_date': self.last_subscription_date.isoformat() if self.last_subscription_date else None,
            'last_subscription_end_date': self.last_subscription_end_date.isoformat() if self.last_subscription_end_date else None,
            'last_subscription_amount': self.last_subscription_amount,
            'billing_address': self.billing_address,
            'total_links_created': self.total_links_created,
            'total_qrs_created': self.total_qrs_created,
            'total_clicks': self.total_clicks,
            'deletion_reason': self.deletion_reason,
            'deleted_by': self.deleted_by
        }

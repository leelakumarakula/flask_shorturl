import hmac
import hashlib
import json
import datetime
from flask import current_app
from app.extensions import db
from app.models.webhook_events import WebhookEvent
from app.models.subscription import Subscription, RazorpaySubscriptionPlan
from app.models.user import User
from app.models.plan import Plan
from app.models.billing_info import BillingInfo


def verify_webhook_signature(payload_body, signature, secret):
    """
    Verify Razorpay webhook signature
    
    Args:
        payload_body: Raw request body as bytes or string
        signature: X-Razorpay-Signature header value
        secret: Webhook secret from Razorpay dashboard
    
    Returns:
        bool: True if signature is valid, False otherwise
    """
    try:
        if isinstance(payload_body, str):
            payload_body = payload_body.encode('utf-8')
        
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload_body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        print(f"ERROR: Signature verification failed: {str(e)}")
        return False


def store_webhook_event(event_data, signature):
    """
    Store webhook event in database
    
    Args:
        event_data: Parsed JSON webhook payload
        signature: Webhook signature
    
    Returns:
        WebhookEvent: Created webhook event record or None if duplicate
    """
    try:
        event_id = event_data.get('event')
        # Use a combination of event and created_at for unique ID if event field is not unique
        # Razorpay uses 'event' for event type, not unique ID
        # Check for 'id' field in the payload
        unique_event_id = event_data.get('id', f"{event_id}_{event_data.get('created_at', datetime.datetime.utcnow().timestamp())}")
        
        # Check if event already exists (idempotency)
        existing_event = WebhookEvent.query.filter_by(event_id=unique_event_id).first()
        if existing_event:
            print(f"DEBUG: Webhook event {unique_event_id} already exists, skipping")
            return None
        
        # Extract metadata
        event_type = event_data.get('event', 'unknown')
        payload_obj = event_data.get('payload', {})
        
        # Try to extract subscription and payment IDs
        subscription_id = None
        payment_id = None
        user_id = None
        
        # Check payment entity
        payment_entity = payload_obj.get('payment', {}).get('entity', {})
        if payment_entity:
            payment_id = payment_entity.get('id')
        
        # Check subscription entity
        subscription_entity = payload_obj.get('subscription', {}).get('entity', {})
        if subscription_entity:
            subscription_id = subscription_entity.get('id')
            # Try to get user_id from subscription notes
            notes = subscription_entity.get('notes', {})
            if isinstance(notes, dict):
                user_id = notes.get('user_id')
        
        # Create webhook event record
        webhook_event = WebhookEvent(
            event_id=unique_event_id,
            event_type=event_type,
            payload=json.dumps(event_data),
            signature=signature,
            processed=False,
            subscription_id=subscription_id,
            payment_id=payment_id,
            user_id=user_id,
            created_at=datetime.datetime.utcnow()
        )
        
        db.session.add(webhook_event)
        db.session.commit()
        
        print(f"DEBUG: Stored webhook event {unique_event_id} - {event_type}")
        return webhook_event
        
    except Exception as e:
        print(f"ERROR: Failed to store webhook event: {str(e)}")
        db.session.rollback()
        return None


def process_payment_authorized(event_data, webhook_event):
    """Process payment.authorized event"""
    try:
        payload = event_data.get('payload', {})
        payment_entity = payload.get('payment', {}).get('entity', {})
        payment_id = payment_entity.get('id')
        
        print(f"DEBUG: Processing payment.authorized for payment {payment_id}")
        
        # Update webhook event as processed
        webhook_event.processed = True
        webhook_event.processed_at = datetime.datetime.utcnow()
        db.session.commit()
        
        return True
    except Exception as e:
        error_msg = f"Failed to process payment.authorized: {str(e)}"
        print(f"ERROR: {error_msg}")
        webhook_event.error_message = error_msg
        db.session.commit()
        return False


def process_payment_captured(event_data, webhook_event):
    """Process payment.captured event - Activate subscription"""
    try:
        payload = event_data.get('payload', {})
        payment_entity = payload.get('payment', {}).get('entity', {})
        subscription_entity = payload.get('subscription', {}).get('entity', {})
        
        payment_id = payment_entity.get('id')
        subscription_id = subscription_entity.get('id') if subscription_entity else None
        
        print(f"DEBUG: Processing payment.captured for payment {payment_id}, subscription {subscription_id}")
        
        if not subscription_id:
            # Try to find subscription from payment notes
            notes = payment_entity.get('notes', {})
            if isinstance(notes, dict):
                subscription_id = notes.get('subscription_id')
        
        if subscription_id:
            # Find subscription in database
            sub = Subscription.query.filter_by(razorpay_subscription_id=subscription_id).first()
            
            if sub:
                # Update subscription status
                sub.subscription_status = 'Active'
                sub.is_active = True
                
                now_utc = datetime.datetime.utcnow()
                sub.subscription_start_date = now_utc
                sub.updated_date = now_utc
                
                # Calculate end date based on plan period
                rz_plan = RazorpaySubscriptionPlan.query.filter_by(razorpay_plan_id=sub.razorpay_plan_id).first()
                if rz_plan:
                    period_lower = (rz_plan.period or "").lower()
                    if "monthly" in period_lower:
                        sub.subscription_end_date = now_utc + datetime.timedelta(days=30)
                    elif "yearly" in period_lower:
                        sub.subscription_end_date = now_utc + datetime.timedelta(days=360)
                    else:
                        sub.subscription_end_date = now_utc + datetime.timedelta(days=30)
                    
                    sub.next_billing_date = sub.subscription_end_date
                    
                    # Link plan to user
                    user = User.query.get(sub.user_id)
                    if user and rz_plan:
                        internal_plan = Plan.query.filter_by(name=rz_plan.plan_name).first()
                        if not internal_plan:
                            # Fallback: partial match
                            all_plans = Plan.query.all()
                            for p in all_plans:
                                if p.name.lower() in rz_plan.plan_name.lower():
                                    internal_plan = p
                                    break
                        
                        if internal_plan:
                            if user.plan_id != internal_plan.id:
                                user.plan_id = internal_plan.id
                                # CLEAR Custom Limits on Plan CHANGE only
                                user.custom_limits = None
                                print(f"DEBUG: Updated User {user.id} to NEW Plan ID {internal_plan.id} (Limits Cleared)")
                            else:
                                print(f"DEBUG: User {user.id} renewed same Plan ID {internal_plan.id} (Limits Preserved)")
                    
                    # Update billing info
                    billing_info = BillingInfo.query.filter_by(user_id=sub.user_id).order_by(BillingInfo.created_at.desc()).first()
                    if billing_info:
                        billing_info.razorpay_plan_id = sub.razorpay_plan_id
                        billing_info.razorpay_subscription_id = subscription_id
                
                db.session.commit()
                print(f"DEBUG: Activated subscription {subscription_id} via webhook")
            else:
                print(f"WARNING: Subscription {subscription_id} not found in database")
        
        # Mark webhook as processed
        webhook_event.processed = True
        webhook_event.processed_at = datetime.datetime.utcnow()
        db.session.commit()
        
        return True
        
    except Exception as e:
        error_msg = f"Failed to process payment.captured: {str(e)}"
        print(f"ERROR: {error_msg}")
        webhook_event.error_message = error_msg
        db.session.commit()
        return False


def process_payment_failed(event_data, webhook_event):
    """Process payment.failed event"""
    try:
        payload = event_data.get('payload', {})
        payment_entity = payload.get('payment', {}).get('entity', {})
        subscription_entity = payload.get('subscription', {}).get('entity', {})
        
        payment_id = payment_entity.get('id')
        subscription_id = subscription_entity.get('id') if subscription_entity else None
        
        print(f"DEBUG: Processing payment.failed for payment {payment_id}, subscription {subscription_id}")
        
        if subscription_id:
            sub = Subscription.query.filter_by(razorpay_subscription_id=subscription_id).first()
            if sub:
                sub.subscription_status = 'Failed'
                sub.is_active = False
                sub.updated_date = datetime.datetime.utcnow()
                db.session.commit()
                print(f"DEBUG: Marked subscription {subscription_id} as Failed")
        
        webhook_event.processed = True
        webhook_event.processed_at = datetime.datetime.utcnow()
        db.session.commit()
        
        return True
        
    except Exception as e:
        error_msg = f"Failed to process payment.failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        webhook_event.error_message = error_msg
        db.session.commit()
        return False


def process_subscription_activated(event_data, webhook_event):
    """Process subscription.activated event - Full activation with plan linking"""
    try:
        payload = event_data.get('payload', {})
        subscription_entity = payload.get('subscription', {}).get('entity', {})
        subscription_id = subscription_entity.get('id')
        
        print(f"DEBUG: Processing subscription.activated for {subscription_id}")
        
        if subscription_id:
            sub = Subscription.query.filter_by(razorpay_subscription_id=subscription_id).first()
            
            if sub and sub.subscription_status != 'Active':
                # Activate subscription
                sub.subscription_status = 'Active'
                sub.is_active = True
                
                now_utc = datetime.datetime.utcnow()
                sub.subscription_start_date = now_utc
                sub.updated_date = now_utc
                
                # Calculate end date based on plan period
                rz_plan = RazorpaySubscriptionPlan.query.filter_by(razorpay_plan_id=sub.razorpay_plan_id).first()
                if rz_plan:
                    period_lower = (rz_plan.period or "").lower()
                    if "monthly" in period_lower:
                        sub.subscription_end_date = now_utc + datetime.timedelta(days=30)
                    elif "yearly" in period_lower:
                        sub.subscription_end_date = now_utc + datetime.timedelta(days=360)
                    else:
                        sub.subscription_end_date = now_utc + datetime.timedelta(days=30)
                    
                    sub.next_billing_date = sub.subscription_end_date
                    
                    # Link plan to user
                    user = User.query.get(sub.user_id)
                    if user and rz_plan:
                        internal_plan = Plan.query.filter_by(name=rz_plan.plan_name).first()
                        if not internal_plan:
                            # Fallback: partial match
                            all_plans = Plan.query.all()
                            for p in all_plans:
                                if p.name.lower() in rz_plan.plan_name.lower():
                                    internal_plan = p
                                    break
                        
                        if internal_plan:
                            if user.plan_id != internal_plan.id:
                                user.plan_id = internal_plan.id
                                # CLEAR Custom Limits on Plan CHANGE only
                                user.custom_limits = None
                                print(f"DEBUG: Updated User {user.id} to NEW Plan ID {internal_plan.id} (Limits Cleared)")
                            else:
                                print(f"DEBUG: User {user.id} renewed same Plan ID {internal_plan.id} (Limits Preserved)")
                    
                    # Update billing info
                    billing_info = BillingInfo.query.filter_by(user_id=sub.user_id).order_by(BillingInfo.created_at.desc()).first()
                    if billing_info:
                        billing_info.razorpay_plan_id = sub.razorpay_plan_id
                        billing_info.razorpay_subscription_id = subscription_id
                
                db.session.commit()
                print(f"DEBUG: Activated subscription {subscription_id} via subscription.activated event")
            elif sub and sub.subscription_status == 'Active':
                # Already active, just update timestamp
                sub.updated_date = datetime.datetime.utcnow()
                db.session.commit()
                print(f"DEBUG: Subscription {subscription_id} already active, updated timestamp")
        
        webhook_event.processed = True
        webhook_event.processed_at = datetime.datetime.utcnow()
        db.session.commit()
        
        return True
        
    except Exception as e:
        error_msg = f"Failed to process subscription.activated: {str(e)}"
        print(f"ERROR: {error_msg}")
        webhook_event.error_message = error_msg
        db.session.commit()
        return False


def process_subscription_cancelled(event_data, webhook_event):
    """Process subscription.cancelled event"""
    try:
        payload = event_data.get('payload', {})
        subscription_entity = payload.get('subscription', {}).get('entity', {})
        subscription_id = subscription_entity.get('id')
        
        print(f"DEBUG: Processing subscription.cancelled for {subscription_id}")
        
        if subscription_id:
            sub = Subscription.query.filter_by(razorpay_subscription_id=subscription_id).first()
            if sub:
                sub.subscription_status = 'Cancelled'
                sub.is_active = False
                sub.updated_date = datetime.datetime.utcnow()
                db.session.commit()
                print(f"DEBUG: Cancelled subscription {subscription_id}")
        
        webhook_event.processed = True
        webhook_event.processed_at = datetime.datetime.utcnow()
        db.session.commit()
        
        return True
        
    except Exception as e:
        error_msg = f"Failed to process subscription.cancelled: {str(e)}"
        print(f"ERROR: {error_msg}")
        webhook_event.error_message = error_msg
        db.session.commit()
        return False


def process_webhook_event(event_data, signature):
    """
    Main webhook processing function
    
    Args:
        event_data: Parsed JSON webhook payload
        signature: Webhook signature
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Store the webhook event
        webhook_event = store_webhook_event(event_data, signature)
        
        if not webhook_event:
            return True, "Duplicate event, already processed"
        
        event_type = event_data.get('event', '')
        
        # Route to appropriate handler based on event type
        if event_type == 'payment.authorized':
            success = process_payment_authorized(event_data, webhook_event)
        elif event_type == 'payment.captured':
            success = process_payment_captured(event_data, webhook_event)
        elif event_type == 'payment.failed':
            success = process_payment_failed(event_data, webhook_event)
        elif event_type == 'subscription.activated':
            success = process_subscription_activated(event_data, webhook_event)
        elif event_type == 'subscription.cancelled':
            success = process_subscription_cancelled(event_data, webhook_event)
        elif event_type == 'subscription.charged':
            # Handle recurring payment
            success = process_payment_captured(event_data, webhook_event)
        else:
            # Unknown event type, just mark as processed
            print(f"DEBUG: Unknown event type {event_type}, storing only")
            webhook_event.processed = True
            webhook_event.processed_at = datetime.datetime.utcnow()
            db.session.commit()
            success = True
        
        if success:
            return True, f"Event {event_type} processed successfully"
        else:
            return False, f"Failed to process event {event_type}"
            
    except Exception as e:
        error_msg = f"Webhook processing error: {str(e)}"
        print(f"ERROR: {error_msg}")
        return False, error_msg

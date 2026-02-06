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
        # Log full payload for debugging
        print(f"DEBUG: Full webhook payload: {json.dumps(event_data, indent=2)}")
        
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
        
        # Initialize variables
        subscription_id = None
        payment_id = None
        user_id = None
        invoice_id = None
        order_id = None
        
        # Extract payment data - try multiple paths
        # Path 1: payload.payment.entity (nested structure)
        payment_entity = payload_obj.get('payment', {}).get('entity', {})
        
        # Path 2: If nested structure is empty, try direct payment object
        if not payment_entity or not payment_entity.get('id'):
            payment_entity = payload_obj.get('payment', {})
        
        if payment_entity and payment_entity.get('id'):
            payment_id = payment_entity.get('id')
            invoice_id = payment_entity.get('invoice_id')
            order_id = payment_entity.get('order_id')
            
            # Try to get user_id from payment notes (notes can be dict or array)
            payment_notes = payment_entity.get('notes', {})
            if isinstance(payment_notes, dict) and payment_notes.get('user_id'):
                user_id = payment_notes.get('user_id')
                print(f"DEBUG: Extracted user_id from payment notes: {user_id}")
            
            # Also try to get subscription_id from payment entity
            if payment_entity.get('subscription_id'):
                subscription_id = payment_entity.get('subscription_id')
                print(f"DEBUG: Extracted subscription_id from payment entity: {subscription_id}")
            
            print(f"DEBUG: Extracted payment_id: {payment_id}, invoice_id: {invoice_id}, order_id: {order_id}")
        
        # Extract subscription data - try multiple paths
        # Path 1: payload.subscription.entity (nested structure)
        subscription_entity = payload_obj.get('subscription', {}).get('entity', {})
        
        # Path 2: If nested structure is empty, try direct subscription object
        if not subscription_entity or not subscription_entity.get('id'):
            subscription_entity = payload_obj.get('subscription', {})
        
        if subscription_entity and subscription_entity.get('id'):
            subscription_id = subscription_entity.get('id')
            
            # Try to get user_id from subscription notes (overrides payment user_id if present)
            subscription_notes = subscription_entity.get('notes', {})
            if isinstance(subscription_notes, dict) and subscription_notes.get('user_id'):
                user_id = subscription_notes.get('user_id')
                print(f"DEBUG: Extracted user_id from subscription notes: {user_id}")
            
            print(f"DEBUG: Extracted subscription_id: {subscription_id}")
        
        # Fallback 1: If still no user_id or subscription_id, try to find from database using subscription_id
        if subscription_id and not user_id:
            from app.models.subscription import Subscription
            sub = Subscription.query.filter_by(razorpay_subscription_id=subscription_id).first()
            if sub:
                user_id = sub.user_id
                print(f"DEBUG: Found user_id {user_id} from database using subscription_id")
        
        # Fallback 2: If we have payment_id but no subscription_id, search for related subscription events
        # Payment events (payment.authorized, payment.captured) come BEFORE subscription.charged
        # But subscription.charged includes BOTH payment and subscription data
        # So we search for a subscription event with the same payment_id
        if payment_id and not subscription_id:
            print(f"DEBUG: Searching for subscription using payment_id: {payment_id}")
            # Search in webhook_events for subscription.charged or subscription.activated with this payment_id
            related_event = WebhookEvent.query.filter(
                WebhookEvent.payment_id == payment_id,
                WebhookEvent.subscription_id.isnot(None)
            ).first()
            
            if related_event:
                subscription_id = related_event.subscription_id
                user_id = related_event.user_id
                print(f"DEBUG: Found subscription_id {subscription_id} and user_id {user_id} from related webhook event")
        
        # Fallback 3: If still no subscription_id/user_id, try to find by invoice_id
        # The invoice_id links payment to subscription
        if invoice_id and (not subscription_id or not user_id):
            print(f"DEBUG: Searching for subscription using invoice_id pattern: {invoice_id}")
            from app.models.subscription import Subscription
            
            # Search recent subscriptions and check if invoice_id appears in their webhook events
            recent_webhook = WebhookEvent.query.filter(
                WebhookEvent.payload.like(f'%{invoice_id}%'),
                WebhookEvent.subscription_id.isnot(None)
            ).first()
            
            if recent_webhook:
                if not subscription_id:
                    subscription_id = recent_webhook.subscription_id
                if not user_id:
                    user_id = recent_webhook.user_id
                print(f"DEBUG: Found subscription_id {subscription_id} and user_id {user_id} using invoice_id search")
        
        print(f"DEBUG: Final extracted values - Event: {event_type}, Payment ID: {payment_id}, Subscription ID: {subscription_id}, User ID: {user_id}")

        
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
        import traceback
        traceback.print_exc()
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
                            user.plan_id = internal_plan.id
                            print(f"DEBUG: Updated User {user.id} to Plan ID {internal_plan.id}")
                    
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
                            user.plan_id = internal_plan.id
                            print(f"DEBUG: Updated User {user.id} to Plan ID {internal_plan.id}")
                    
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

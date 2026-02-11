import hmac
import hashlib
import json
import datetime
from flask import current_app
from app.extensions import db
from app.models.webhook_events import WebhookEvent
from app.models.subscription import Subscription, RazorpaySubscriptionPlan
from app.models.subscription_history import SubscriptionHistory
from app.models.user import User
from app.models.plan import Plan
from app.models.billing_info import BillingInfo
import requests
from app.routes.subscription_routes import _downgrade_user_to_free
 
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
                                # RESET Usage Counters on Plan CHANGE/UPGRADE
                                user.usage_links = 0
                                user.usage_qrs = 0
                                user.usage_qr_with_logo = 0
                                user.usage_editable_links = 0
                                print(f"DEBUG: Updated User {user.id} to NEW Plan ID {internal_plan.id} (Limits & Usage Counters Reset)")
                            else:
                                if not user.permanent_custom_limits:
                                    user.custom_limits = None
                                # RESET Usage Counters on Plan RENEWAL
                                user.usage_links = 0
                                user.usage_qrs = 0
                                user.usage_qr_with_logo = 0
                                user.usage_editable_links = 0
                                print(f"DEBUG: User {user.id} renewed same Plan ID {internal_plan.id} (Usage Counters Reset)")
                   
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
    """Process payment.failed event - Mark subscription as failed and downgrade user"""
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
                print(f"DEBUG: Marked subscription {subscription_id} as Failed (User plan remains unchanged)")
       
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
                                # RESET Usage Counters on Plan CHANGE/UPGRADE
                                user.usage_links = 0
                                user.usage_qrs = 0
                                user.usage_qr_with_logo = 0
                                user.usage_editable_links = 0
                                print(f"DEBUG: Updated User {user.id} to NEW Plan ID {internal_plan.id} (Limits & Usage Counters Reset)")
                            else:
                                if not user.permanent_custom_limits:
                                    user.custom_limits = None
                                # RESET Usage Counters on Plan RENEWAL
                                user.usage_links = 0
                                user.usage_qrs = 0
                                user.usage_qr_with_logo = 0
                                user.usage_editable_links = 0
                                print(f"DEBUG: User {user.id} renewed same Plan ID {internal_plan.id} (Usage Counters Reset)")
                   
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
                # Update subscription end_date from payload if available
                current_end = subscription_entity.get('current_end')
                if current_end:
                    sub.subscription_end_date = datetime.datetime.utcfromtimestamp(current_end)
                    print(f"DEBUG: Updated subscription {subscription_id} end_date to {sub.subscription_end_date} from webhook")

                # Create subscription history record before updating
                try:
                    history = SubscriptionHistory(
                        subscription_id=sub.razorpay_subscription_id,
                        user_id=sub.user_id,
                        razorpay_plan_id=sub.razorpay_plan_id,
                        plan_amount=sub.plan_amount,
                        cancelled_date=datetime.datetime.utcnow(),
                        cancelled_reason='Webhook Cancellation',
                        subscription_start_date=sub.subscription_start_date,
                        subscription_end_date=sub.subscription_end_date,
                        is_active=True,
                        card_id=sub.card_id,
                        total_count=sub.total_count,
                        notes=sub.notes
                    )
                    db.session.add(history)
                    print(f"DEBUG: Created subscription history for {subscription_id}")
                except Exception as e:
                    print(f"WARNING: Failed to create subscription history: {str(e)}")
                
                # Update subscription status
                sub.subscription_status = 'Cancelled'
                sub.is_active = False
                sub.updated_date = datetime.datetime.utcnow()
                
                # Check for OTHER active subscriptions (e.g. from an upgrade)
                # If another active subscription exists, DO NOT downgrade the user
                other_active_sub = Subscription.query.filter_by(
                    user_id=sub.user_id,
                    is_active=True
                ).filter(
                    Subscription.id != sub.id,
                    Subscription.subscription_status.in_(['Active', 'Authenticated'])
                ).first()

                if other_active_sub:
                    print(f"DEBUG: User {sub.user_id} has another active subscription {other_active_sub.razorpay_subscription_id}. SKIPPING downgrade to Free.")
                else:
                    # Downgrade user to Free plan ONLY if no other active subscription exists
                    user = User.query.get(sub.user_id)
                    if user:
                        _downgrade_user_to_free(user.id)
                        # free_plan = Plan.query.filter_by(name='Free').first()
                        # if free_plan:
                        #     user.plan_id = free_plan.id
                        #     user.custom_limits = None
                        #     # Set usage counters to Free plan limits (not zero)
                        #     # This gives users the full Free plan quota
                        #     user.usage_links = free_plan.max_links if free_plan.max_links != -1 else 0
                        #     user.usage_qrs = free_plan.max_qrs if free_plan.max_qrs != -1 else 0
                        #     user.usage_qr_with_logo = free_plan.max_qr_with_logo if free_plan.max_qr_with_logo != -1 else 0
                        #     user.usage_editable_links = free_plan.max_editable_links if free_plan.max_editable_links != -1 else 0
                        print(f"DEBUG: Downgraded user {user.id} to Free plan with limits: links={user.usage_links}, qrs={user.usage_qrs}")
                
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
 
 

def process_subscription_authenticated(event_data, webhook_event):
    """Process subscription.authenticated event - Activate subscription"""
    try:
        payload = event_data.get('payload', {})
        subscription_entity = payload.get('subscription', {}).get('entity', {})
       
        subscription_id = subscription_entity.get('id')
       
        print(f"DEBUG: Processing subscription.authenticated for subscription {subscription_id}")
       
        if subscription_id:
            # Find subscription in database
            sub = Subscription.query.filter_by(razorpay_subscription_id=subscription_id).first()
           
            if sub:
                # Update subscription status
                sub.subscription_status = 'Active'
                sub.is_active = True
               
                # Update timestamps from payload (Unix timestamp to UTC)
                current_start = subscription_entity.get('current_start')
                current_end = subscription_entity.get('current_end')
                
                now_utc = datetime.datetime.utcnow()
                sub.updated_date = now_utc
                
                if current_start:
                    sub.subscription_start_date = datetime.datetime.utcfromtimestamp(current_start)
                else:
                    sub.subscription_start_date = now_utc
                    
                if current_end:
                    sub.subscription_end_date = datetime.datetime.utcfromtimestamp(current_end)
                    sub.next_billing_date = sub.subscription_end_date
                else:
                    # Fallback if current_end is missing: calculate based on plan period
                    rz_plan = RazorpaySubscriptionPlan.query.filter_by(razorpay_plan_id=sub.razorpay_plan_id).first()
                    days = 30 # Default
                    if rz_plan:
                        period_lower = (rz_plan.period or "").lower()
                        if "monthly" in period_lower:
                            days = 30
                        elif "yearly" in period_lower:
                            days = 360
                    
                    sub.subscription_end_date = now_utc + datetime.timedelta(days=days)
                    sub.next_billing_date = sub.subscription_end_date

                # Get plan details for linking user
                rz_plan = RazorpaySubscriptionPlan.query.filter_by(razorpay_plan_id=sub.razorpay_plan_id).first()
                
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
                            # RESET Usage Counters on Plan CHANGE/UPGRADE
                            user.usage_links = 0
                            user.usage_qrs = 0
                            user.usage_qr_with_logo = 0
                            user.usage_editable_links = 0
                            print(f"DEBUG: Updated User {user.id} to NEW Plan ID {internal_plan.id} (Limits & Usage Counters Reset)")
                        else:
                            if not user.permanent_custom_limits:
                                user.custom_limits = None
                            # RESET Usage Counters on Plan RENEWAL
                            user.usage_links = 0
                            user.usage_qrs = 0
                            user.usage_qr_with_logo = 0
                            user.usage_editable_links = 0
                            print(f"DEBUG: User {user.id} renewed same Plan ID {internal_plan.id} (Usage Counters Reset)")
                
                # Update billing info
                billing_info = BillingInfo.query.filter_by(user_id=sub.user_id).order_by(BillingInfo.created_at.desc()).first()
                if billing_info:
                    billing_info.razorpay_plan_id = sub.razorpay_plan_id
                    billing_info.razorpay_subscription_id = subscription_id
               
                db.session.commit()
                print(f"DEBUG: Activated subscription {subscription_id} via subscription.authenticated")

                # ============================================================================
                # CANCEL PREVIOUS ACTIVE SUBSCRIPTIONS (DEFERRED CANCELLATION)
                # ============================================================================
                try:
                    # Find other active subscriptions for this user
                    other_active_subs = Subscription.query.filter_by(
                        user_id=sub.user_id,
                        is_active=True
                    ).filter(
                        Subscription.id != sub.id,  # Exclude current new subscription
                        Subscription.subscription_status.in_(['Active', 'Authenticated'])
                    ).all()

                    for old_sub in other_active_subs:
                        print(f"DEBUG: Found previous active subscription {old_sub.razorpay_subscription_id}, cancelling now")
                        _cancel_old_subscription(old_sub)
                        
                except Exception as e:
                    print(f"WARNING: Failed to process deferred cancellation: {str(e)}")

            else:
                print(f"WARNING: Subscription {subscription_id} not found in database")
       
        # Mark webhook as processed
        webhook_event.processed = True
        webhook_event.processed_at = datetime.datetime.utcnow()
        db.session.commit()
       
        return True
       
    except Exception as e:
        error_msg = f"Failed to process subscription.authenticated: {str(e)}"
        print(f"ERROR: {error_msg}")
        webhook_event.error_message = error_msg
        db.session.commit()
        return False


def _cancel_old_subscription(subscription):
    """
    Helper to cancel an old subscription via Razorpay API and create history
    """
    try:
        razorpay_key_id = current_app.config.get('RAZORPAY_KEY_ID')
        razorpay_key_secret = current_app.config.get('RAZORPAY_KEY_SECRET')
        
        if not razorpay_key_id or not razorpay_key_secret:
            print("ERROR: Razorpay credentials missing for cancellation")
            return

        # 1. Call Razorpay API
        url = f"https://api.razorpay.com/v1/subscriptions/{subscription.razorpay_subscription_id}/cancel"
        payload = {"cancel_at_cycle_end": False} # Cancel immediately upon upgrade
        
        response = requests.post(
            url,
            json=payload,
            auth=(razorpay_key_id, razorpay_key_secret)
        )
        
        if response.status_code == 200:
            print(f"DEBUG: Razorpay cancellation successful for {subscription.razorpay_subscription_id}")
        else:
            print(f"WARNING: Razorpay cancellation failed for {subscription.razorpay_subscription_id}: {response.text}")
            # We proceed to mark it cancelled locally anyway to avoid double billing/access

        # 2. Create History Record
        history = SubscriptionHistory(
            subscription_id=subscription.razorpay_subscription_id,
            user_id=subscription.user_id,
            razorpay_plan_id=subscription.razorpay_plan_id,
            plan_amount=subscription.plan_amount,
            cancelled_date=datetime.datetime.utcnow(),
            cancelled_reason='Upgrade to New Plan (Webhook)',
            subscription_start_date=subscription.subscription_start_date,
            subscription_end_date=subscription.subscription_end_date,
            is_active=True,
            card_id=subscription.card_id,
            total_count=subscription.total_count,
            notes=subscription.notes
        )
        db.session.add(history)

        # 3. Update Subscription Status
        subscription.subscription_status = 'Cancelled'
        subscription.is_active = False
        subscription.updated_date = datetime.datetime.utcnow()
        
        db.session.commit()
        print(f"DEBUG: deferred cancellation completed for {subscription.razorpay_subscription_id}")

    except Exception as e:
        print(f"ERROR: Error in _cancel_old_subscription: {str(e)}")



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
        if event_type == 'subscription.authenticated':
            success = process_subscription_authenticated(event_data, webhook_event)
        elif event_type == 'subscription.cancelled':
            success = process_subscription_cancelled(event_data, webhook_event)
        elif event_type == 'payment.failed':
            success = process_payment_failed(event_data, webhook_event)
        else:
            # All other events are ignored/marked processed without action as per new requirement
            # 'payment.authorized', 'payment.captured', 'subscription.activated', 'subscription.charged'
            print(f"DEBUG: Event type {event_type} ignored/skipped (marking processed)")
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
 
 
from flask import Blueprint, request, jsonify, current_app
import json
from app.extensions import db
from app.models.subscription import RazorpaySubscriptionPlan, Subscription
from app.models.subscription import RazorpaySubscriptionPlan, Subscription
from app.models.subscription_history import SubscriptionHistory
from app.models.user import User
from app.models.plan import Plan
from app.models.webhook_events import WebhookEvent
from app.routes.auth_routes import token_required
import requests
import base64
import hmac
import hashlib
import datetime

from threading import Lock

subscription_bp = Blueprint('subscription_bp', __name__)
plan_lock = Lock()
subscription_lock = Lock()

@subscription_bp.route('/create_plan', methods=['POST'])
@token_required
def create_plan(current_user):
    with plan_lock:
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No input data provided'}), 400

            period = data.get('period')
            interval = data.get('interval')
            item = data.get('item')
            notes = data.get('notes')

            if not all([period, interval, item]):
                 return jsonify({'error': 'Missing required fields: period, interval, item'}), 400

            # Check for existing plan to prevent duplicates
            plan_name = item.get('name')
            existing_plan = RazorpaySubscriptionPlan.query.filter_by(
                plan_name=plan_name,
                period=period,
                interval=interval
            ).first()

            if existing_plan:
                 print(f"DEBUG: Returning existing plan {existing_plan.razorpay_plan_id} for {plan_name}")
                 return jsonify({
                    'message': 'Plan retrieved successfully',
                    'plan': {
                        'id': existing_plan.id,
                        'razorpay_plan_id': existing_plan.razorpay_plan_id,
                        'plan_name': existing_plan.plan_name
                    }
                }), 200

            # Razorpay API Call
            razorpay_key_id = current_app.config.get('RAZORPAY_KEY_ID')
            razorpay_key_secret = current_app.config.get('RAZORPAY_KEY_SECRET')

            if not razorpay_key_id or not razorpay_key_secret:
                 return jsonify({'error': 'Razorpay credentials not configured'}), 500

            url = "https://api.razorpay.com/v1/plans"
            
            # Requests handles Basic Auth automatically
            response = requests.post(
                url,
                json={
                    "period": period,
                    "interval": interval,
                    "item": item,
                    "notes": notes
                },
                auth=(razorpay_key_id, razorpay_key_secret)
            )

            if response.status_code != 200:
                print(f"DEBUG: Razorpay Plan Creation Failed: {response.text}")
                return jsonify({'error': 'Razorpay API failed', 'details': response.json()}), response.status_code

            razorpay_data = response.json()
            razorpay_plan_id = razorpay_data.get('id')

            # Create Database Record
            new_plan = RazorpaySubscriptionPlan(
                plan_name=item.get('name'),
                razorpay_plan_id=razorpay_plan_id,
                period=period,
                interval=interval,
                amount=item.get('amount') / 100.0 if item.get('amount') else 0.0, # Assuming amount is in paise
                is_active=True,
                pro_rated_amount=0.0 # Default
            )

            db.session.add(new_plan)
            db.session.commit()
            
            print(f"DEBUG: Created new plan {razorpay_plan_id} for {plan_name}")

            return jsonify({
                'message': 'Plan created successfully',
                'plan': {
                    'id': new_plan.id,
                    'razorpay_plan_id': new_plan.razorpay_plan_id,
                    'plan_name': new_plan.plan_name
                }
            }), 201

        except Exception as e:
            return jsonify({'error': str(e)}), 500


@subscription_bp.route('/create_subscription', methods=['POST'])
@token_required
def create_subscription(current_user):
    with subscription_lock:
        try:
            data = request.get_json()
            plan_id = data.get('plan_id') # Expecting Razorpay Plan ID (e.g. plan_Hw...)

            if not plan_id:
                 return jsonify({'error': 'Missing plan_id'}), 400

            razorpay_key_id = current_app.config.get('RAZORPAY_KEY_ID')
            razorpay_key_secret = current_app.config.get('RAZORPAY_KEY_SECRET')

            if not razorpay_key_id or not razorpay_key_secret:
                 return jsonify({'error': 'Razorpay credentials not configured'}), 500

            # Check for existing PENDING subscription to reuse
            existing_sub = Subscription.query.filter_by(
                user_id=current_user.id,
                razorpay_plan_id=plan_id,
                subscription_status='Pending' # Razorpay status for created but not paid
            ).order_by(Subscription.created_date.desc()).first()

            if existing_sub:
                 print(f"DEBUG: Reuse existing Pending Subscription {existing_sub.razorpay_subscription_id}")
                 return jsonify({
                    'razorpay_subscription_id': existing_sub.razorpay_subscription_id,
                    'key_id': razorpay_key_id,
                    'status': existing_sub.subscription_status
                }), 200
            
            # Get additional parameters
            total_count = data.get('total_count', 12)
            quantity = data.get('quantity', 1)
            customer_notify = data.get('customer_notify', 1)
            addons = data.get('addons')
            offer_id = data.get('offer_id')
            notes = data.get('notes', {})

            # Ensure notes has user info
            if not notes: notes = {}
            notes['user_id'] = current_user.id
            notes['email'] = current_user.email

            payload = {
                "plan_id": plan_id,
                "total_count": total_count,
                "quantity": quantity,
                "customer_notify": customer_notify,
                "notes": notes
            }

            # Add optional fields if present
            if addons: payload['addons'] = addons
            if offer_id: payload['offer_id'] = offer_id
            
            url = "https://api.razorpay.com/v1/subscriptions"
            
            response = requests.post(
                url,
                json=payload,
                auth=(razorpay_key_id, razorpay_key_secret)
            )

            if response.status_code != 200:
                return jsonify({'error': 'Failed to create subscription', 'details': response.json()}), response.status_code
            
            sub_data = response.json()
            sub_id = sub_data.get('id')

            # Fetch plan details to get the amount
            fetched_plan = RazorpaySubscriptionPlan.query.filter_by(razorpay_plan_id=plan_id).first()
            plan_amount_val = fetched_plan.amount if fetched_plan else 0.0

            # Create Subscription Record
            new_sub = Subscription(
                user_id=current_user.id,
                razorpay_plan_id=plan_id,
                razorpay_subscription_id=sub_id,
                subscription_status='Pending',
                created_date=datetime.datetime.utcnow(),
                # next_billing_date will be updated upon activation
                next_billing_date=datetime.datetime.utcnow(),
                total_count=total_count,
                customer_notify=bool(customer_notify),
                addons=str(addons) if addons else None,
                offer_id=offer_id,
                notes=json.dumps(notes),
                plan_amount=plan_amount_val,
                ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
                short_url=sub_data.get('short_url')
            )
            
            db.session.add(new_sub)
            db.session.commit()

            return jsonify({
                'razorpay_subscription_id': sub_id,
                'key_id': razorpay_key_id
            }), 200

        except Exception as e:
             return jsonify({'error': str(e)}), 500


@subscription_bp.route('/create_plan_and_subscription', methods=['POST'])
@token_required
def create_plan_and_subscription(current_user):
    """Combined endpoint to create plan and subscription in one call"""
    with plan_lock:
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No input data provided'}), 400

            # Extract plan data
            plan_data = data.get('plan')
            if not plan_data:
                return jsonify({'error': 'Missing plan data'}), 400

            period = plan_data.get('period')
            interval = plan_data.get('interval')
            item = plan_data.get('item')
            notes = plan_data.get('notes')

            if not all([period, interval, item]):
                return jsonify({'error': 'Missing required plan fields: period, interval, item'}), 400

            # Check for existing plan to prevent duplicates
            plan_name = item.get('name')
            existing_plan = RazorpaySubscriptionPlan.query.filter_by(
                plan_name=plan_name,
                period=period,
                interval=interval
            ).first()

            razorpay_key_id = current_app.config.get('RAZORPAY_KEY_ID')
            razorpay_key_secret = current_app.config.get('RAZORPAY_KEY_SECRET')

            if not razorpay_key_id or not razorpay_key_secret:
                return jsonify({'error': 'Razorpay credentials not configured'}), 500

            # Create or get plan
            if existing_plan:
                print(f"DEBUG: Using existing plan {existing_plan.razorpay_plan_id} for {plan_name}")
                razorpay_plan_id = existing_plan.razorpay_plan_id
            else:
                # Create new plan on Razorpay
                url = "https://api.razorpay.com/v1/plans"
                response = requests.post(
                    url,
                    json={
                        "period": period,
                        "interval": interval,
                        "item": item,
                        "notes": notes
                    },
                    auth=(razorpay_key_id, razorpay_key_secret)
                )

                if response.status_code != 200:
                    print(f"DEBUG: Razorpay Plan Creation Failed: {response.text}")
                    return jsonify({'error': 'Razorpay plan creation failed', 'details': response.json()}), response.status_code

                razorpay_data = response.json()
                razorpay_plan_id = razorpay_data.get('id')

                # Create Database Record
                new_plan = RazorpaySubscriptionPlan(
                    plan_name=item.get('name'),
                    razorpay_plan_id=razorpay_plan_id,
                    user_id=current_user.id,
                    period=period,
                    interval=interval,
                    amount=item.get('amount') / 100.0 if item.get('amount') else 0.0,
                    is_active=True,
                    pro_rated_amount=0.0
                )

                db.session.add(new_plan)
                db.session.commit()
                print(f"DEBUG: Created new plan {razorpay_plan_id} for {plan_name}")

            # ============================================================================
            # CANCEL EXISTING ACTIVE SUBSCRIPTION BEFORE UPGRADE
            # ============================================================================
            # Check if user has any active subscription (not Pending, not Cancelled)
            existing_active_sub = Subscription.query.filter_by(
                user_id=current_user.id,
                is_active=True
            ).filter(
                Subscription.subscription_status.in_(['Active', 'Authenticated'])
            ).first()

            if existing_active_sub:
                print(f"DEBUG: Found existing active subscription {existing_active_sub.razorpay_subscription_id}, cancelling before upgrade")
                
                # Cancel the existing subscription in Razorpay (immediate cancellation for upgrades)
                cancel_success, cancel_response = _call_razorpay_cancel_api(
                    existing_active_sub.razorpay_subscription_id, 
                    cancel_at_cycle_end=False  # Immediate cancellation for upgrades
                )
                
                if cancel_success:
                    # Create history record for the cancelled subscription
                    _create_subscription_history(existing_active_sub, 'Upgrade to New Plan')
                    
                    # Update the existing subscription status
                    existing_active_sub.subscription_status = 'Cancelled'
                    existing_active_sub.is_active = False
                    existing_active_sub.updated_date = datetime.datetime.utcnow()
                    
                    db.session.commit()
                    print(f"DEBUG: Successfully cancelled existing subscription {existing_active_sub.razorpay_subscription_id}")
                else:
                    # Log warning but continue with upgrade (user might have manually cancelled)
                    print(f"WARNING: Failed to cancel existing subscription in Razorpay: {cancel_response}")
                    # Still update local status
                    existing_active_sub.subscription_status = 'Cancelled'
                    existing_active_sub.is_active = False
                    existing_active_sub.updated_date = datetime.datetime.utcnow()
                    db.session.commit()

            # Check for existing PENDING subscription to reuse
            existing_sub = Subscription.query.filter_by(
                user_id=current_user.id,
                razorpay_plan_id=razorpay_plan_id,
                subscription_status='Pending'
            ).order_by(Subscription.created_date.desc()).first()

            if existing_sub:
                print(f"DEBUG: Reuse existing Pending Subscription {existing_sub.razorpay_subscription_id}")
                return jsonify({
                    'razorpay_subscription_id': existing_sub.razorpay_subscription_id,
                    'razorpay_plan_id': razorpay_plan_id,
                    'key_id': razorpay_key_id,
                    'status': existing_sub.subscription_status
                }), 200

            # Create subscription on Razorpay
            subscription_data = data.get('subscription', {})
            # total_count = subscription_data.get('total_count', 12)
            quantity = subscription_data.get('quantity', 1)
            customer_notify = subscription_data.get('customer_notify', 1)
            addons = subscription_data.get('addons')
            offer_id = subscription_data.get('offer_id')
            sub_notes = subscription_data.get('notes', {})

            # Ensure notes has user info
            if not sub_notes:
                sub_notes = {}
            sub_notes['user_id'] = current_user.id
            sub_notes['email'] = current_user.email
            plan_data = RazorpaySubscriptionPlan.query.filter_by(razorpay_plan_id=razorpay_plan_id).first()
            if plan_data.period == 'yearly':
                total_count = 25
            else:
                total_count = 350
            payload = {
                "plan_id": razorpay_plan_id,
                "total_count": total_count,
                "quantity": quantity,
                "customer_notify": customer_notify,
                "notes": sub_notes
            }

            # Add optional fields if present
            if addons:
                payload['addons'] = addons
            if offer_id:
                payload['offer_id'] = offer_id

            url = "https://api.razorpay.com/v1/subscriptions"
            response = requests.post(
                url,
                json=payload,
                auth=(razorpay_key_id, razorpay_key_secret)
            )

            if response.status_code != 200:
                return jsonify({'error': 'Failed to create subscription', 'details': response.json()}), response.status_code

            sub_data = response.json()
            print(f"DEBUG: Created subscription {sub_data}")
            sub_id = sub_data.get('id')

            # Fetch plan details to get the amount
            fetched_plan = RazorpaySubscriptionPlan.query.filter_by(razorpay_plan_id=razorpay_plan_id).first()
            plan_amount_val = fetched_plan.amount if fetched_plan else 0.0

            # Create Subscription Record
            new_sub = Subscription(
                user_id=current_user.id,
                razorpay_plan_id=razorpay_plan_id,
                razorpay_subscription_id=sub_id,
                subscription_status='Pending',
                created_date=datetime.datetime.utcnow(),
                # subscription_start_date and next_billing_date will be updated upon activation
                subscription_start_date=None,
                next_billing_date=None,
                total_count=total_count,
                customer_notify=bool(customer_notify),
                addons=str(addons) if addons else None,
                offer_id=offer_id,
                notes=json.dumps(sub_notes),
                plan_amount=plan_amount_val,
                ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
                short_url=sub_data.get('short_url')
            )

            db.session.add(new_sub)
            db.session.commit()

            return jsonify({
                'razorpay_subscription_id': sub_id,
                'razorpay_plan_id': razorpay_plan_id,
                'key_id': razorpay_key_id,
                'razorpay_response': sub_data
            }), 200

        except Exception as e:
            return jsonify({'error': str(e)}), 500



@subscription_bp.route('/verify_payment', methods=['POST'])
@token_required
def verify_payment(current_user):
    """
    Verify payment signature and check subscription status.
    This endpoint ONLY checks status - all activation is handled by webhooks.
    """
    try:
        data = request.get_json()
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_subscription_id = data.get('razorpay_subscription_id')
        razorpay_signature = data.get('razorpay_signature')

        if not all([razorpay_payment_id, razorpay_subscription_id, razorpay_signature]):
            return jsonify({'error': 'Missing payment details'}), 400

        # Verify signature for security
        razorpay_key_secret = current_app.config.get('RAZORPAY_KEY_SECRET')
        msg = f"{razorpay_payment_id}|{razorpay_subscription_id}"
        generated_signature = hmac.new(
            bytes(razorpay_key_secret, 'latin-1'),
            msg=bytes(msg, 'latin-1'),
            digestmod=hashlib.sha256
        ).hexdigest()

        if generated_signature != razorpay_signature:
            return jsonify({'error': 'Invalid signature'}), 400

        # Get subscription
        sub = Subscription.query.filter_by(razorpay_subscription_id=razorpay_subscription_id).first()
        
        if not sub:
            return jsonify({'error': 'Subscription not found'}), 404
        
        # Store the verified signature
        sub.razorpay_signature_id = razorpay_signature
        db.session.commit()
        print(f"DEBUG: Stored razorpay_signature for subscription {razorpay_subscription_id}")

        # Check if webhook has processed this payment
        webhook_processed = WebhookEvent.query.filter_by(
            subscription_id=razorpay_subscription_id,
            processed=True
        ).filter(
            WebhookEvent.event_type.in_(['payment.captured', 'subscription.activated'])
        ).first()

        # Return current status based on webhook processing
        if webhook_processed and sub.subscription_status == 'Active':
            print(f"DEBUG: Webhook processed and subscription active for {razorpay_subscription_id}")
            return jsonify({
                'message': 'Subscription verified and activated by webhook',
                'status': 'Active',
                'subscription_id': razorpay_subscription_id,
                'webhook_processed': True
            }), 200
        elif sub.subscription_status == 'Active':
            print(f"DEBUG: Subscription already active for {razorpay_subscription_id}")
            return jsonify({
                'message': 'Subscription is active',
                'status': 'Active',
                'subscription_id': razorpay_subscription_id,
                'webhook_processed': bool(webhook_processed)
            }), 200
        else:
            # Payment verified but webhook hasn't processed yet
            print(f"INFO: Payment verified but webhook pending for {razorpay_subscription_id}")
            return jsonify({
                'message': 'Payment verified, waiting for webhook to activate subscription',
                'status': sub.subscription_status,
                'subscription_id': razorpay_subscription_id,
                'webhook_processed': False,
                'note': 'Subscription will be activated automatically by webhook'
            }), 202  # 202 Accepted - processing in progress

    except Exception as e:
        print(f"ERROR: verify_payment failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


@subscription_bp.route('/save_billing_info', methods=['POST'])
@token_required
def save_billing_info(current_user):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No input data provided'}), 400

        # Validate required fields
        required_fields = ['first_name', 'email', 'phone_number']
        if not all(data.get(field) for field in required_fields):
             return jsonify({'error': 'Missing required fields'}), 400

        from app.models.billing_info import BillingInfo

        # Create new Billing Info record
        billing_info = BillingInfo(
            user_id=current_user.id,
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            email=data.get('email'),
            phone_number=data.get('phone_number'),
            address=data.get('address'),
            amount=data.get('amount'),
            plan_id=data.get('plan_id')
        )

        db.session.add(billing_info)
        db.session.commit()

        return jsonify({'message': 'Billing info saved successfully', 'id': billing_info.id}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# HELPER FUNCTIONS FOR SUBSCRIPTION CANCELLATION
# ============================================================================

def _call_razorpay_cancel_api(subscription_id, cancel_at_cycle_end=True):
    """
    Call Razorpay API to cancel a subscription
    
    Args:
        subscription_id: Razorpay subscription ID
        cancel_at_cycle_end: If True, cancel at end of billing cycle. If False, cancel immediately.
    
    Returns:
        tuple: (success: bool, response_data: dict or error_message: str)
    """
    try:
        razorpay_key_id = current_app.config.get('RAZORPAY_KEY_ID')
        razorpay_key_secret = current_app.config.get('RAZORPAY_KEY_SECRET')

        if not razorpay_key_id or not razorpay_key_secret:
            return False, 'Razorpay credentials not configured'

        url = f"https://api.razorpay.com/v1/subscriptions/{subscription_id}/cancel"
        
        payload = {
            "cancel_at_cycle_end": cancel_at_cycle_end
        }

        response = requests.post(
            url,
            json=payload,
            auth=(razorpay_key_id, razorpay_key_secret)
        )

        if response.status_code == 200:
            return True, response.json()
        else:
            error_data = response.json() if response.text else {'error': 'Unknown error'}
            return False, error_data

    except Exception as e:
        return False, str(e)


def _create_subscription_history(subscription, reason='User Requested'):
    """
    Create a subscription history record from an existing subscription
    
    Args:
        subscription: Subscription object
        reason: Reason for cancellation
    
    Returns:
        SubscriptionHistory object
    """
    try:
        history = SubscriptionHistory(
            subscription_id=subscription.razorpay_subscription_id,
            user_id=subscription.user_id,
            razorpay_plan_id=subscription.razorpay_plan_id,
            plan_amount=subscription.plan_amount,
            cancelled_date=datetime.datetime.utcnow(),
            cancelled_reason=reason,
            subscription_start_date=subscription.subscription_start_date,
            subscription_end_date=subscription.subscription_end_date,
            is_active=True,
            card_id=subscription.card_id,
            total_count=subscription.total_count,
            notes=subscription.notes
        )
        
        db.session.add(history)
        return history
    except Exception as e:
        print(f"ERROR: Failed to create subscription history: {str(e)}")
        raise


def _downgrade_user_to_free(user_id):
    """
    Downgrade user to Free plan and reset usage counters
    
    Args:
        user_id: User ID to downgrade
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return False
        
        # Find Free plan
        free_plan = Plan.query.filter_by(name='Free').first()
        if not free_plan:
            print("WARNING: Free plan not found in database")
            return False
        
        # Update user plan
        user.plan_id = free_plan.id
        user.custom_limits = None
        
        # Set usage counters to Free plan limits (not zero)
        # This gives users the full Free plan quota
        user.usage_links = free_plan.max_links if free_plan.max_links != -1 else 0
        user.usage_qrs = free_plan.max_qrs if free_plan.max_qrs != -1 else 0
        user.usage_qr_with_logo = free_plan.max_qr_with_logo if free_plan.max_qr_with_logo != -1 else 0
        user.usage_editable_links = free_plan.max_editable_links if free_plan.max_editable_links != -1 else 0
        
        print(f"DEBUG: Downgraded user {user_id} to Free plan with limits: links={user.usage_links}, qrs={user.usage_qrs}")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to downgrade user: {str(e)}")
        return False


# ============================================================================
# CANCEL SUBSCRIPTION ENDPOINTS
# ============================================================================

@subscription_bp.route('/cancel_subscription', methods=['POST'])
@token_required
def cancel_subscription(current_user):
    """
    Cancel a subscription immediately or at cycle end
    
    Request Body:
        razorpay_subscription_id: Razorpay subscription ID
        cancel_at_cycle_end: (optional) True to cancel at cycle end, False for immediate (default: True)
        cancelled_reason: (optional) Reason for cancellation (default: 'User Requested')
    """
    try:
        data = request.get_json()
        subscription_id = data.get('razorpay_subscription_id')
        cancel_at_cycle_end = data.get('cancel_at_cycle_end', True)
        cancelled_reason = data.get('cancelled_reason', 'User Requested')

        if not subscription_id:
            return jsonify({'error': 'Missing razorpay_subscription_id'}), 400

        # Find subscription in database
        subscription = Subscription.query.filter_by(
            razorpay_subscription_id=subscription_id,
            user_id=current_user.id
        ).first()

        if not subscription:
            return jsonify({'error': 'Subscription not found'}), 404

        # Check if already cancelled
        if subscription.subscription_status == 'Cancelled':
            return jsonify({'error': 'Subscription already cancelled'}), 400

        # Call Razorpay API to cancel subscription
        success, response_data = _call_razorpay_cancel_api(subscription_id, cancel_at_cycle_end)

        if not success:
            return jsonify({
                'error': 'Failed to cancel subscription with Razorpay',
                'details': response_data
            }), 500

        # Create subscription history record
        _create_subscription_history(subscription, cancelled_reason)

        # Update subscription status
        subscription.subscription_status = 'Cancelled'
        subscription.is_active = False
        subscription.updated_date = datetime.datetime.utcnow()

        # If immediate cancellation, downgrade user to Free plan
        if not cancel_at_cycle_end:
            _downgrade_user_to_free(current_user.id)

        db.session.commit()

        print(f"DEBUG: Cancelled subscription {subscription_id} for user {current_user.id}")

        return jsonify({
            'message': 'Subscription cancelled successfully',
            'subscription_id': subscription_id,
            'cancel_at_cycle_end': cancel_at_cycle_end,
            'razorpay_response': response_data
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"ERROR: cancel_subscription failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


@subscription_bp.route('/subscription_history', methods=['GET'])
@token_required
def get_subscription_history(current_user):
    """
    Get subscription history for the current user
    
    Returns:
        List of subscription history records
    """
    try:
        history_records = SubscriptionHistory.query.filter_by(
            user_id=current_user.id
        ).order_by(SubscriptionHistory.cancelled_date.desc()).all()

        return jsonify({
            'history': [record.to_dict() for record in history_records]
        }), 200

    except Exception as e:
        print(f"ERROR: get_subscription_history failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


@subscription_bp.route('/active_subscription', methods=['GET'])
@token_required
def get_active_subscription(current_user):
    """
    Get the current active subscription for the user
    
    Returns:
        Active subscription details or null if no active subscription
    """
    try:
        active_sub = Subscription.query.filter_by(
            user_id=current_user.id,
            is_active=True
        ).order_by(Subscription.created_date.desc()).first()

        if not active_sub:
            return jsonify({
                'subscription': None,
                'message': 'No active subscription found'
            }), 200

        # Get plan details
        plan = RazorpaySubscriptionPlan.query.filter_by(
            razorpay_plan_id=active_sub.razorpay_plan_id
        ).first()

        subscription_data = {
            'id': active_sub.id,
            'razorpay_subscription_id': active_sub.razorpay_subscription_id,
            'razorpay_plan_id': active_sub.razorpay_plan_id,
            'plan_name': plan.plan_name if plan else 'Unknown',
            'plan_amount': active_sub.plan_amount,
            'subscription_status': active_sub.subscription_status,
            'subscription_start_date': active_sub.subscription_start_date.isoformat() if active_sub.subscription_start_date else None,
            'subscription_end_date': active_sub.subscription_end_date.isoformat() if active_sub.subscription_end_date else None,
            'next_billing_date': active_sub.next_billing_date.isoformat() if active_sub.next_billing_date else None,
            'created_date': active_sub.created_date.isoformat() if active_sub.created_date else None
        }

        return jsonify({
            'subscription': subscription_data
        }), 200

    except Exception as e:
        print(f"ERROR: get_active_subscription failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


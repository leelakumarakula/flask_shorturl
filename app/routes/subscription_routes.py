from flask import Blueprint, request, jsonify, current_app
from app.extensions import db
from app.models.subscription import RazorpaySubscriptionPlan, Subscription
from app.models.subscription import RazorpaySubscriptionPlan, Subscription
from app.models.user import User
from app.models.plan import Plan
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
            start_at = data.get('start_at')
            expire_by = data.get('expire_by')
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
            if start_at: payload['start_at'] = start_at
            if expire_by: payload['expire_by'] = expire_by
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
                next_billing_date=datetime.datetime.utcnow(),
                total_count=total_count,
                customer_notify=bool(customer_notify),
                start_at=start_at,
                expire_by=expire_by,
                addons=str(addons) if addons else None,
                offer_id=offer_id,
                notes=str(notes),
                plan_amount=plan_amount_val
            )
            
            db.session.add(new_sub)
            db.session.commit()

            return jsonify({
                'razorpay_subscription_id': sub_id,
                'key_id': razorpay_key_id
            }), 200

        except Exception as e:
             return jsonify({'error': str(e)}), 500


@subscription_bp.route('/verify_payment', methods=['POST'])
@token_required
def verify_payment(current_user):
    try:
        data = request.get_json()
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_subscription_id = data.get('razorpay_subscription_id')
        razorpay_signature = data.get('razorpay_signature')

        if not all([razorpay_payment_id, razorpay_subscription_id, razorpay_signature]):
            return jsonify({'error': 'Missing payment details'}), 400

        razorpay_key_secret = current_app.config.get('RAZORPAY_KEY_SECRET')
        
        # Verify Signature
        msg = f"{razorpay_payment_id}|{razorpay_subscription_id}"
        generated_signature = hmac.new(
            bytes(razorpay_key_secret, 'latin-1'),
            msg=bytes(msg, 'latin-1'),
            digestmod=hashlib.sha256
        ).hexdigest()

        if generated_signature != razorpay_signature:
             return jsonify({'error': 'Invalid signature'}), 400

        # Update Subscription Status
        sub = Subscription.query.filter_by(razorpay_subscription_id=razorpay_subscription_id).first()
        if sub:
            sub.subscription_status = 'Active'
            sub.is_active = True
            sub.razorpay_signature_id = razorpay_signature # Storing signature as requested in model? Model has `razorpay_signature_id`
            sub.razorpay_payment_id = razorpay_payment_id # Wait, model didn't have payment_id? It had card_id.
            # Model has `razorpay_signature_id`. I'll put signature there.
            
            sub.subscription_start_date = datetime.datetime.utcnow()
            # Next billing date logic dependent on plan interval, Razorpay manages it but we might want to store it.
            # For now update start date.
            
            # Link plan to user
            # Find the plan using razorpay_plan_id
            rz_plan = RazorpaySubscriptionPlan.query.filter_by(razorpay_plan_id=sub.razorpay_plan_id).first()
            print(f"DEBUG: Found Razorpay Plan: {rz_plan}")
            if rz_plan:
                 print(f"DEBUG: Plan Name from Razorpay: {rz_plan.plan_name}")
                 # Check 'app/models/plan.py' to see if we can map this generic Razorpay plan to our internal Plan ID
                 internal_plan = Plan.query.filter_by(name=rz_plan.plan_name).first()
                 print(f"DEBUG: Internal Plan Found: {internal_plan}")
                 if internal_plan:
                     current_user.plan_id = internal_plan.id
                     print(f"DEBUG: Updated User {current_user.id} to Plan ID {internal_plan.id}")
                 else:
                     # Fallback: Check if internal plan name is part of razorpay plan name (e.g. "Pro" in "pro plan - monthly")
                     all_plans = Plan.query.all()
                     print(f"DEBUG: Exact match failed. Searching through {len(all_plans)} plans...")
                     for p in all_plans:
                         if p.name.lower() in rz_plan.plan_name.lower():
                             internal_plan = p
                             print(f"DEBUG: Found Partial Match: {p.name} in {rz_plan.plan_name}")
                             break
                     
                     if internal_plan:
                         current_user.plan_id = internal_plan.id
                         print(f"DEBUG: Updated User {current_user.id} to Plan ID {internal_plan.id} (Fallback)")

            
            db.session.commit()
            return jsonify({'message': 'Subscription verified and activated'}), 200
            
            db.session.commit()
            return jsonify({'message': 'Subscription verified and activated'}), 200
        else:
            return jsonify({'error': 'Subscription not found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

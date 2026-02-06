from flask import Blueprint, request, jsonify, current_app
from app.services.webhook_service import verify_webhook_signature, process_webhook_event
import json

webhook_bp = Blueprint('webhook_bp', __name__)


@webhook_bp.route('/webhook', methods=['POST'])
def razorpay_webhook():
    """
    Razorpay webhook endpoint - NO AUTHENTICATION REQUIRED
    This endpoint receives payment and subscription events from Razorpay
    """
    try:
        # Get raw request body for signature verification
        payload_body = request.get_data()
        
        # Get signature from headers
        signature = request.headers.get('X-Razorpay-Signature')
        
        if not signature:
            print("ERROR: Missing X-Razorpay-Signature header")
            return jsonify({'error': 'Missing signature'}), 400
        
        # Get webhook secret from config
        webhook_secret = current_app.config.get('RAZORPAY_WEBHOOK_SECRET')
        
        if not webhook_secret:
            print("ERROR: RAZORPAY_WEBHOOK_SECRET not configured")
            return jsonify({'error': 'Webhook not configured'}), 500
        
        # Verify signature
        if not verify_webhook_signature(payload_body, signature, webhook_secret):
            print("ERROR: Invalid webhook signature")
            return jsonify({'error': 'Invalid signature'}), 401
        
        # Parse JSON payload
        try:
            event_data = json.loads(payload_body)
        except json.JSONDecodeError:
            print("ERROR: Invalid JSON payload")
            return jsonify({'error': 'Invalid JSON'}), 400
        
        event_type = event_data.get('event', 'unknown')
        print(f"DEBUG: Received webhook event: {event_type}")
        
        # Process the webhook event
        success, message = process_webhook_event(event_data, signature)
        
        if success:
            print(f"DEBUG: Webhook processed successfully: {message}")
            # Always return 200 to acknowledge receipt
            return jsonify({'status': 'success', 'message': message}), 200
        else:
            print(f"ERROR: Webhook processing failed: {message}")
            # Still return 200 to prevent Razorpay from retrying
            # The error is logged in the database
            return jsonify({'status': 'error', 'message': message}), 200
            
    except Exception as e:
        error_msg = f"Webhook handler error: {str(e)}"
        print(f"ERROR: {error_msg}")
        # Return 200 to prevent retries, error is logged
        return jsonify({'status': 'error', 'message': error_msg}), 200


@webhook_bp.route('/webhook/test', methods=['GET'])
def webhook_test():
    """Test endpoint to verify webhook is accessible"""
    return jsonify({
        'status': 'ok',
        'message': 'Webhook endpoint is accessible',
        'configured': bool(current_app.config.get('RAZORPAY_WEBHOOK_SECRET'))
    }), 200

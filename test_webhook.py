"""
Test script for webhook integration
Run this to verify the webhook endpoint is working correctly
"""

import requests
import json
import hmac
import hashlib

# Configuration
BASE_URL = "http://localhost:5000"
WEBHOOK_URL = f"{BASE_URL}/api/subscription/webhook"
TEST_URL = f"{BASE_URL}/api/subscription/webhook/test"

# Test webhook secret (use actual secret from .env for real testing)
WEBHOOK_SECRET = "test_secret_key"

def test_webhook_accessibility():
    """Test if webhook endpoint is accessible"""
    print("Testing webhook accessibility...")
    try:
        response = requests.get(TEST_URL)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

def generate_signature(payload_body, secret):
    """Generate HMAC-SHA256 signature for webhook"""
    if isinstance(payload_body, str):
        payload_body = payload_body.encode('utf-8')
    
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return signature

def test_webhook_with_sample_payload():
    """Test webhook with a sample payment.captured event"""
    print("\nTesting webhook with sample payload...")
    
    # Sample webhook payload
    payload = {
        "id": "event_test_" + str(int(1000000)),
        "event": "payment.captured",
        "created_at": 1234567890,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test123",
                    "amount": 50000,
                    "currency": "INR",
                    "status": "captured",
                    "method": "card"
                }
            },
            "subscription": {
                "entity": {
                    "id": "sub_test123",
                    "status": "active",
                    "notes": {
                        "user_id": 1,
                        "email": "test@example.com"
                    }
                }
            }
        }
    }
    
    payload_body = json.dumps(payload)
    signature = generate_signature(payload_body, WEBHOOK_SECRET)
    
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature
    }
    
    try:
        response = requests.post(WEBHOOK_URL, data=payload_body, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("Webhook Integration Test Suite")
    print("=" * 60)
    
    # Test 1: Accessibility
    test1_passed = test_webhook_accessibility()
    
    # Test 2: Sample payload (will fail signature verification with default secret)
    # Uncomment this after setting up actual webhook secret
    # test2_passed = test_webhook_with_sample_payload()
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print(f"  Accessibility Test: {'✓ PASSED' if test1_passed else '✗ FAILED'}")
    # print(f"  Payload Test: {'✓ PASSED' if test2_passed else '✗ FAILED'}")
    print("=" * 60)
    
    print("\nNext Steps:")
    print("1. Add RAZORPAY_WEBHOOK_SECRET to .env file")
    print("2. Configure webhook URL in Razorpay Dashboard")
    print("3. Test with real payment")
    print("4. Monitor webhook_events table in database")

if __name__ == "__main__":
    main()

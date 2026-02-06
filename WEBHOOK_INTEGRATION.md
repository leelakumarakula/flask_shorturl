# Razorpay Webhook Integration - Setup Guide

## Overview

This application now supports automatic payment confirmation via Razorpay webhooks. When a payment is completed, Razorpay will automatically notify your server, which will update the subscription status without requiring the frontend to call the `verify_payment` API.

## Architecture

### Webhook Flow
1. User completes payment on Razorpay checkout
2. Razorpay sends webhook event to `/api/subscription/webhook`
3. Server verifies signature and stores event in `webhook_events` table
4. Server processes event and updates subscription status
5. User's plan is automatically activated

### Fallback Flow
The existing `verify_payment` endpoint remains available as a fallback mechanism. It checks if the webhook has already processed the payment to prevent duplicate confirmations.

## Configuration

### 1. Database Setup

Run the SQL migration to create the `webhook_events` table:

```bash
# Connect to your database and run:
# c:\Users\Leela\Desktop\VBLUELINK\flask_shorturl\create_webhook_events_table.sql
```

Or let Flask create it automatically on next startup (already configured in `app/__init__.py`).

### 2. Environment Variables

Add the webhook secret to your `.env` file:

```env
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_from_razorpay_dashboard
```

**How to get the webhook secret:**
1. Log into [Razorpay Dashboard](https://dashboard.razorpay.com/)
2. Go to Settings → Webhooks
3. Create a new webhook or view existing webhook
4. Copy the "Secret" value

### 3. Razorpay Dashboard Configuration

Configure the webhook in Razorpay Dashboard:

**Webhook URL:** `https://your-domain.com/api/subscription/webhook`

For local testing: `http://your-ngrok-url/api/subscription/webhook`

**Active Events to Select:**
- ✅ payment.authorized
- ✅ payment.captured
- ✅ payment.failed
- ✅ subscription.activated
- ✅ subscription.charged
- ✅ subscription.cancelled

**Alert Email:** `cloudops@vayublue.com` (or your preferred email)

## API Endpoints

### Webhook Endpoint (Public)
```
POST /api/subscription/webhook
```

**Headers:**
- `Content-Type: application/json`
- `X-Razorpay-Signature: <signature>`

**Body:** Razorpay webhook payload (varies by event type)

**Response:** Always returns 200 OK to acknowledge receipt

### Test Endpoint
```
GET /api/subscription/webhook/test
```

Verify webhook endpoint is accessible and configured.

**Response:**
```json
{
  "status": "ok",
  "message": "Webhook endpoint is accessible",
  "configured": true
}
```

### Verify Payment (Fallback)
```
POST /api/subscription/verify_payment
Authorization: Bearer <token>
```

**Body:**
```json
{
  "razorpay_payment_id": "pay_xxx",
  "razorpay_subscription_id": "sub_xxx",
  "razorpay_signature": "signature_xxx"
}
```

**Response:**
```json
{
  "message": "Subscription verified and activated",
  "source": "webhook" | "api_verification" | "previous_verification"
}
```

## Database Schema

### webhook_events Table

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR(36) | Primary key (UUID) |
| event_id | VARCHAR(255) | Razorpay event ID (unique) |
| event_type | VARCHAR(100) | Event type (e.g., payment.captured) |
| payload | TEXT | Complete JSON payload |
| signature | VARCHAR(512) | Webhook signature |
| processed | BOOLEAN | Processing status |
| created_at | DATETIME | Event received timestamp |
| processed_at | DATETIME | Event processed timestamp |
| error_message | TEXT | Any processing errors |
| subscription_id | VARCHAR(255) | Razorpay subscription ID |
| payment_id | VARCHAR(255) | Razorpay payment ID |
| user_id | INT | User ID |

## Event Handling

### payment.authorized
- Stores event in database
- Marks as processed

### payment.captured
- **Activates subscription**
- Updates subscription status to "Active"
- Sets subscription start and end dates
- Links plan to user
- Updates billing info

### payment.failed
- Marks subscription as "Failed"
- Deactivates subscription

### subscription.activated
- Updates subscription status to "Active"
- Sets activation timestamp

### subscription.cancelled
- Marks subscription as "Cancelled"
- Deactivates subscription

### subscription.charged
- Handles recurring payments
- Same logic as payment.captured

## Testing

### Local Testing with ngrok

1. Start your Flask application:
```bash
python app.py
```

2. Start ngrok tunnel:
```bash
ngrok http 5000
```

3. Configure webhook URL in Razorpay Dashboard with ngrok URL

4. Test webhook endpoint:
```bash
curl http://localhost:5000/api/subscription/webhook/test
```

### Manual Testing

Test with a sample webhook payload:

```bash
curl -X POST http://localhost:5000/api/subscription/webhook \
  -H "Content-Type: application/json" \
  -H "X-Razorpay-Signature: test_signature" \
  -d '{
    "event": "payment.captured",
    "payload": {
      "payment": {
        "entity": {
          "id": "pay_test123",
          "amount": 50000,
          "status": "captured"
        }
      },
      "subscription": {
        "entity": {
          "id": "sub_test123"
        }
      }
    }
  }'
```

## Monitoring

### Check Webhook Events

Query the database to see received webhooks:

```sql
-- Recent webhook events
SELECT event_id, event_type, processed, created_at, processed_at
FROM webhook_events
ORDER BY created_at DESC
LIMIT 10;

-- Failed webhook processing
SELECT event_id, event_type, error_message, created_at
FROM webhook_events
WHERE processed = 0 OR error_message IS NOT NULL
ORDER BY created_at DESC;

-- Events for specific subscription
SELECT *
FROM webhook_events
WHERE subscription_id = 'sub_xxx'
ORDER BY created_at DESC;
```

### Application Logs

Look for these log messages:
- `DEBUG: Received webhook event: <event_type>`
- `DEBUG: Webhook processed successfully: <message>`
- `DEBUG: Activated subscription <id> via webhook`
- `ERROR: Webhook processing failed: <message>`

## Security

### Signature Verification
All webhook requests are verified using HMAC-SHA256 signature verification. Invalid signatures are rejected with 401 Unauthorized.

### Idempotency
Duplicate events (same `event_id`) are automatically detected and skipped to prevent duplicate processing.

### Error Handling
All webhook processing errors are logged in the `webhook_events` table with error messages for debugging.

## Troubleshooting

### Webhook not receiving events
1. Check webhook URL is publicly accessible
2. Verify webhook is active in Razorpay Dashboard
3. Check firewall/security group settings
4. Review Razorpay Dashboard webhook logs

### Signature verification failing
1. Verify `RAZORPAY_WEBHOOK_SECRET` is correct
2. Check for extra whitespace in .env file
3. Ensure webhook secret matches Razorpay Dashboard

### Subscription not activating
1. Check `webhook_events` table for the event
2. Review `error_message` column for processing errors
3. Verify subscription exists in `subscriptions` table
4. Check application logs for detailed error messages

### Duplicate processing
The system handles this automatically:
- Webhook events are deduplicated by `event_id`
- `verify_payment` checks if webhook already processed the payment
- Subscription status checks prevent duplicate activation

## Migration from verify_payment

The `verify_payment` endpoint is still fully functional and can be used as a fallback. However, with webhooks configured:

1. **Primary flow:** Webhook automatically confirms payment
2. **Fallback flow:** Frontend can still call `verify_payment` if needed
3. **Duplicate prevention:** Both methods check for existing confirmations

No frontend changes are required immediately. The webhook will work alongside the existing flow.

## Production Deployment

1. ✅ Add `RAZORPAY_WEBHOOK_SECRET` to production environment variables
2. ✅ Run database migration to create `webhook_events` table
3. ✅ Deploy updated application code
4. ✅ Configure webhook URL in Razorpay Dashboard (production mode)
5. ✅ Test with a real payment
6. ✅ Monitor webhook events in database and logs

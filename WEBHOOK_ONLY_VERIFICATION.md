# Webhook-Only Payment Verification

## Overview

The `verify_payment` endpoint has been simplified to **ONLY check status**. All subscription activation is handled exclusively by webhooks.

---

## How It Works

### Payment Flow

```
User Pays → Razorpay → Webhook → Activate Subscription
                ↓
         Frontend calls verify_payment
                ↓
         Returns current status
```

### verify_payment Endpoint

**Purpose:** Status checker only - NO activation logic

**What it does:**
1. ✅ Verifies payment signature (security)
2. ✅ Checks if webhook processed the payment
3. ✅ Returns current subscription status
4. ❌ **Does NOT activate subscription**
5. ❌ **Does NOT update dates**
6. ❌ **Does NOT link plans**

---

## API Reference

### Request
```http
POST /api/subscription/verify_payment
Authorization: Bearer <token>
Content-Type: application/json

{
  "razorpay_payment_id": "pay_xxx",
  "razorpay_subscription_id": "sub_xxx",
  "razorpay_signature": "signature_xxx"
}
```

### Response Scenarios

#### 1. Webhook Processed & Active ✅
```json
{
  "message": "Subscription verified and activated by webhook",
  "status": "Active",
  "subscription_id": "sub_xxx",
  "webhook_processed": true
}
```
**Status Code:** 200

#### 2. Active (No Webhook Record)
```json
{
  "message": "Subscription is active",
  "status": "Active",
  "subscription_id": "sub_xxx",
  "webhook_processed": false
}
```
**Status Code:** 200

#### 3. Webhook Pending ⏳
```json
{
  "message": "Payment verified, waiting for webhook to activate subscription",
  "status": "Pending",
  "subscription_id": "sub_xxx",
  "webhook_processed": false,
  "note": "Subscription will be activated automatically by webhook"
}
```
**Status Code:** 202 (Accepted - Processing)

#### 4. Invalid Signature ❌
```json
{
  "error": "Invalid signature"
}
```
**Status Code:** 400

#### 5. Not Found ❌
```json
{
  "error": "Subscription not found"
}
```
**Status Code:** 404

---

## Frontend Integration

### Recommended Approach

```javascript
razorpay.on('payment.success', async function(response) {
  // Call verify_payment to check status
  const result = await fetch('/api/subscription/verify_payment', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      razorpay_payment_id: response.razorpay_payment_id,
      razorpay_subscription_id: response.razorpay_subscription_id,
      razorpay_signature: response.razorpay_signature
    })
  });
  
  const data = await result.json();
  
  if (result.status === 200) {
    // Subscription is active
    console.log('Subscription active!');
    window.location.href = '/dashboard';
  } else if (result.status === 202) {
    // Webhook is processing
    console.log('Activating subscription...');
    // Poll status or show loading message
    setTimeout(() => checkStatus(), 2000);
  } else {
    // Error
    console.error('Payment verification failed:', data.error);
  }
});
```

### Polling for Webhook Processing (Optional)

```javascript
async function checkStatus(subscriptionId, maxAttempts = 5) {
  for (let i = 0; i < maxAttempts; i++) {
    const result = await fetch('/api/subscription/verify_payment', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        razorpay_payment_id: paymentId,
        razorpay_subscription_id: subscriptionId,
        razorpay_signature: signature
      })
    });
    
    const data = await result.json();
    
    if (data.status === 'Active') {
      // Webhook processed!
      return true;
    }
    
    // Wait 2 seconds before next check
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  
  // Webhook taking too long, redirect anyway
  // It will activate in background
  return false;
}
```

---

## Activation Flow

### Webhook Handles Everything

**When webhook receives `payment.captured` or `subscription.activated`:**

1. ✅ Set `subscription_status = 'Active'`
2. ✅ Set `is_active = True`
3. ✅ Calculate dates (start, end, next billing)
4. ✅ Link plan to user
5. ✅ Update billing info
6. ✅ Store webhook event in database

**verify_payment just checks the result**

---

## Benefits

### ✅ Clean Separation of Concerns
- Webhooks = Activation logic
- API = Status checking

### ✅ No Duplicate Activation Logic
- Single source of truth (webhook service)
- Easier to maintain

### ✅ Reliable
- Webhooks retry automatically
- No risk of API activation conflicts

### ✅ Faster
- No database writes in verify_payment
- Just read and return status

---

## Monitoring

### Check Webhook Processing Rate

```sql
-- Subscriptions activated by webhook
SELECT COUNT(*) as webhook_activated
FROM subscriptions s
WHERE subscription_status = 'Active'
AND EXISTS (
  SELECT 1 FROM webhook_events 
  WHERE subscription_id = s.razorpay_subscription_id 
  AND processed = 1
);

-- Total active subscriptions
SELECT COUNT(*) as total_active
FROM subscriptions
WHERE subscription_status = 'Active';
```

### Expected Results
- **webhook_activated ≈ total_active** (99%+)

---

## Troubleshooting

### Subscription Stuck in "Pending"

**Symptom:** `verify_payment` returns 202 with `webhook_processed: false`

**Causes:**
1. Webhook not configured in Razorpay
2. Webhook URL not accessible
3. Webhook secret mismatch
4. Network issues

**Solution:**
1. Check Razorpay Dashboard → Webhooks
2. Verify webhook URL is correct
3. Check `RAZORPAY_WEBHOOK_SECRET` in .env
4. Review webhook endpoint logs
5. Check `webhook_events` table for errors

### Manual Activation (Emergency Only)

If webhook fails completely, you can manually activate via database:

```sql
-- DO NOT USE UNLESS WEBHOOK IS BROKEN
UPDATE subscriptions
SET subscription_status = 'Active',
    is_active = 1,
    subscription_start_date = NOW(),
    subscription_end_date = DATE_ADD(NOW(), INTERVAL 30 DAY),
    updated_date = NOW()
WHERE razorpay_subscription_id = 'sub_xxx';

-- Then link plan to user manually
```

---

## Summary

- ✅ **verify_payment** = Status checker only
- ✅ **Webhooks** = Handle all activation
- ✅ **No duplicate logic** = Cleaner codebase
- ✅ **Reliable** = Webhooks retry automatically
- ✅ **Fast** = No database writes in API

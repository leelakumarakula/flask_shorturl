# User-Specific Razorpay Plans - Quick Start Guide

## What Changed?

✅ Each user now gets their own Razorpay plan ID  
✅ Same plan ID is reused when user renews  
✅ Different plan ID created when user changes plans  

## Migration Steps

### Step 1: Backup Database
```bash
# Backup your database before proceeding!
```

### Step 2: Run Migration

**Option A: Python Script (Recommended)**
```bash
cd c:\Users\Leela\Desktop\VBLUELINK\flask_shorturl
python migrations/migrate_user_specific_plans.py
```

**Option B: SQL Script**
```bash
# Connect to your database and run:
# migrations/update_razorpay_plans_user_specific.sql
```

### Step 3: Verify Migration
```bash
python migrations/verify_user_specific_plans.py
```

## What Happens After Migration?

1. **Old plans are cleared** - They will be recreated as user-specific when users subscribe
2. **New subscriptions** - Each user gets their own plan ID
3. **Renewals** - System automatically reuses existing user-specific plan ID
4. **Upgrades** - New plan ID created for the new plan tier

## Testing

### Test 1: New Subscription
- User subscribes to a plan
- Check logs for: `"Created new user-specific plan {plan_id} for user {user_id}"`

### Test 2: Renewal
- Same user renews same plan
- Check logs for: `"Using existing user-specific plan {plan_id} for user {user_id} (RENEWAL)"`

### Test 3: Upgrade
- User changes from Pro to Premium
- Check logs for: `"Created new user-specific plan"` (for Premium)

## Database Queries

```sql
-- View all user-specific plans
SELECT u.email, rsp.plan_name, rsp.period, rsp.razorpay_plan_id 
FROM razorpay_subscription_plans rsp
JOIN users u ON u.id = rsp.user_id
ORDER BY u.email;

-- Check for duplicates (should return 0 rows)
SELECT user_id, plan_name, period, interval, COUNT(*) 
FROM razorpay_subscription_plans 
GROUP BY user_id, plan_name, period, interval 
HAVING COUNT(*) > 1;
```

## Rollback (If Needed)

If you need to rollback, restore from your database backup.

## Support

Check the full documentation in:
- `walkthrough.md` - Complete implementation details
- `implementation_plan.md` - Original design plan

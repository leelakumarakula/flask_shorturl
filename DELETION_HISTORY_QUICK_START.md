# User Deletion History - Quick Reference

## Table Structure

```sql
CREATE TABLE user_deletion_history (
    -- Identity
    id VARCHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,
    
    -- User Info
    firstname VARCHAR(100) NOT NULL,
    lastname VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    organization VARCHAR(200),
    
    -- Dates
    account_created_at DATETIME NOT NULL,
    account_deleted_at DATETIME NOT NULL,
    
    -- Subscription
    last_subscription_plan VARCHAR(100),
    last_subscription_date DATETIME,
    last_subscription_end_date DATETIME,
    last_subscription_amount FLOAT,
    razorpay_subscription_id VARCHAR(255),
    
    -- Billing
    billing_first_name VARCHAR(100),
    billing_last_name VARCHAR(100),
    billing_email VARCHAR(120),
    billing_phone VARCHAR(20),
    billing_address TEXT,
    
    -- Usage Stats
    total_links_created INT DEFAULT 0,
    total_qrs_created INT DEFAULT 0,
    total_clicks INT DEFAULT 0,
    
    -- Metadata
    deletion_reason VARCHAR(255),
    deleted_by VARCHAR(50) DEFAULT 'user',
    ip_address VARCHAR(50),
    metadata TEXT
);
```

## Setup Instructions

### 1. Run Migration
```bash
# Option A: Using MySQL command line
mysql -u root -p vbluelink < create_user_deletion_history_table.sql

# Option B: Using Python/Flask
python
>>> from app.extensions import db
>>> db.create_all()
```

### 2. Verify Table Creation
```sql
DESCRIBE user_deletion_history;
```

## What Gets Saved

When a user deletes their account, the system automatically saves:

✅ **User Information**
- Name (first + last)
- Email
- Phone number
- Organization

✅ **Account Timeline**
- When account was created
- When account was deleted

✅ **Subscription Details**
- Last active plan
- Subscription start/end dates
- Subscription amount
- Razorpay subscription ID

✅ **Billing Information**
- Billing name
- Billing email & phone
- Billing address

✅ **Usage Statistics**
- Total links created
- Total QR codes generated
- Total clicks received

✅ **Deletion Context**
- Who deleted (user/admin/system)
- IP address
- Optional deletion reason

## Files Created/Modified

### New Files:
1. `app/models/user_deletion_history.py` - Model definition
2. `create_user_deletion_history_table.sql` - Database migration
3. `USER_DELETION_HISTORY.md` - Full documentation

### Modified Files:
1. `app/routes/url_routes.py` - Updated delete_account() function

## Testing the Feature

### 1. Create a test account
```bash
# Use your signup endpoint
```

### 2. Delete the account
```bash
# Use the delete account button in the UI
# Or call the API directly
curl -X DELETE http://localhost:5000/delete-account \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. Verify history was saved
```sql
SELECT * FROM user_deletion_history ORDER BY account_deleted_at DESC LIMIT 1;
```

## Common Queries

### View all deleted accounts
```sql
SELECT 
    email, 
    CONCAT(firstname, ' ', lastname) as name,
    account_deleted_at,
    last_subscription_plan
FROM user_deletion_history
ORDER BY account_deleted_at DESC;
```

### Count deletions by month
```sql
SELECT 
    DATE_FORMAT(account_deleted_at, '%Y-%m') as month,
    COUNT(*) as deletions
FROM user_deletion_history
GROUP BY month
ORDER BY month DESC;
```

### Find specific user
```sql
SELECT * FROM user_deletion_history 
WHERE email = 'user@example.com';
```

### Deletion statistics
```sql
SELECT 
    COUNT(*) as total_deletions,
    AVG(total_links_created) as avg_links,
    AVG(total_qrs_created) as avg_qrs,
    SUM(last_subscription_amount) as lost_revenue
FROM user_deletion_history;
```

## Important Notes

⚠️ **Data Persistence**: This table is NOT deleted when users delete their accounts. It's designed to persist indefinitely for audit purposes.

⚠️ **Privacy**: Ensure proper access controls are in place. Only admins should access this data.

⚠️ **Compliance**: Consider your local data retention laws (GDPR, CCPA, etc.) and implement appropriate policies.

⚠️ **No Foreign Keys**: The `user_id` field is NOT a foreign key to allow data to persist after user deletion.

## Next Steps

1. ✅ Run the migration to create the table
2. ✅ Test account deletion to verify history is saved
3. 📋 Implement admin dashboard to view deletion history (optional)
4. 📋 Set up data retention/anonymization policy (recommended)
5. 📋 Create automated reports for deletion analytics (optional)

# User Deletion History Feature

## Overview
This feature implements a comprehensive audit trail system that preserves user account information even after deletion. This is essential for:
- **Compliance**: Meeting legal requirements for data retention
- **Audit Trails**: Tracking account deletions for security purposes
- **Analytics**: Understanding user churn patterns
- **Customer Support**: Handling post-deletion inquiries

## Database Schema

### Table: `user_deletion_history`

#### User Information Fields
- `id` (VARCHAR(36), PRIMARY KEY): Unique identifier for the deletion record
- `user_id` (INT): Original user ID from the users table
- `firstname` (VARCHAR(100)): User's first name
- `lastname` (VARCHAR(100)): User's last name
- `email` (VARCHAR(120)): User's email address
- `phone` (VARCHAR(20)): User's phone number
- `organization` (VARCHAR(200)): User's organization name

#### Account Timeline
- `account_created_at` (DATETIME): When the account was originally created
- `account_deleted_at` (DATETIME): When the account was deleted

#### Subscription Information
Captures the most recent/last active subscription:
- `last_subscription_plan` (VARCHAR(100)): Plan identifier (e.g., "Pro", "Premium")
- `last_subscription_date` (DATETIME): When the last subscription started
- `last_subscription_end_date` (DATETIME): When it ended or was cancelled
- `last_subscription_amount` (FLOAT): Subscription amount in INR
- `razorpay_subscription_id` (VARCHAR(255)): Razorpay subscription identifier

#### Billing Information
Captures the most recent billing details:
- `billing_first_name` (VARCHAR(100)): Billing first name
- `billing_last_name` (VARCHAR(100)): Billing last name
- `billing_email` (VARCHAR(120)): Billing email
- `billing_phone` (VARCHAR(20)): Billing phone number
- `billing_address` (TEXT): Complete billing address

#### Usage Statistics
Snapshot of user activity at deletion time:
- `total_links_created` (INT): Total number of links created
- `total_qrs_created` (INT): Total number of QR codes generated
- `total_clicks` (INT): Total clicks across all user's links

#### Deletion Metadata
- `deletion_reason` (VARCHAR(255)): Optional reason for deletion
- `deleted_by` (VARCHAR(50)): Who initiated deletion ('user', 'admin', 'system')
- `ip_address` (VARCHAR(50)): IP address from which deletion was requested
- `metadata` (TEXT): Additional JSON metadata for flexibility

## Implementation

### 1. Model Definition
Location: `app/models/user_deletion_history.py`

The model includes:
- All fields defined in the schema
- `to_dict()` method for API responses
- Proper indexing for efficient queries

### 2. Delete Account API Update
Location: `app/routes/url_routes.py` - `delete_account()` function

**Process Flow:**
1. **Capture Data**: Before any deletion, gather:
   - User information from `current_user`
   - Latest subscription from `subscriptions` table
   - Latest billing info from `billing_info` table
   - Usage statistics (links, QRs, total clicks)
   - Request metadata (IP address)

2. **Save History**: Create and save `UserDeletionHistory` record

3. **Delete Data**: Proceed with normal deletion cascade:
   - Analytics records
   - QR code files
   - Redis cache
   - URL records
   - Webhook events
   - Billing info
   - Subscription history
   - Active subscriptions
   - User account

4. **Commit**: Single transaction ensures atomicity

### 3. Database Migration
Location: `create_user_deletion_history_table.sql`

Run this SQL script to create the table:
```bash
mysql -u your_username -p your_database < create_user_deletion_history_table.sql
```

Or using Python/Flask:
```python
from app.extensions import db
from app.models.user_deletion_history import UserDeletionHistory

# Create table
db.create_all()
```

## Usage Examples

### Querying Deletion History

#### Get all deleted accounts
```python
from app.models.user_deletion_history import UserDeletionHistory

deleted_users = UserDeletionHistory.query.all()
for user in deleted_users:
    print(f"{user.email} deleted on {user.account_deleted_at}")
```

#### Find deletion by email
```python
history = UserDeletionHistory.query.filter_by(email='user@example.com').first()
if history:
    print(f"Account deleted on: {history.account_deleted_at}")
    print(f"Last plan: {history.last_subscription_plan}")
    print(f"Total links created: {history.total_links_created}")
```

#### Get deletions in date range
```python
from datetime import datetime, timedelta

thirty_days_ago = datetime.utcnow() - timedelta(days=30)
recent_deletions = UserDeletionHistory.query.filter(
    UserDeletionHistory.account_deleted_at >= thirty_days_ago
).all()
```

#### Analytics: Deletion reasons
```python
from sqlalchemy import func

deletion_stats = db.session.query(
    UserDeletionHistory.deletion_reason,
    func.count(UserDeletionHistory.id)
).group_by(UserDeletionHistory.deletion_reason).all()
```

## API Endpoints (Optional Future Enhancement)

You can create admin endpoints to query deletion history:

### GET /admin/deletion-history
```python
@admin_bp.route('/deletion-history', methods=['GET'])
@admin_required
def get_deletion_history():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    history = UserDeletionHistory.query.order_by(
        UserDeletionHistory.account_deleted_at.desc()
    ).paginate(page=page, per_page=per_page)
    
    return api_response(True, "Deletion history retrieved", {
        'items': [h.to_dict() for h in history.items],
        'total': history.total,
        'pages': history.pages,
        'current_page': page
    })
```

### GET /admin/deletion-history/<user_id>
```python
@admin_bp.route('/deletion-history/<int:user_id>', methods=['GET'])
@admin_required
def get_user_deletion_history(user_id):
    history = UserDeletionHistory.query.filter_by(user_id=user_id).first()
    
    if not history:
        return api_response(False, "No deletion record found", None)
    
    return api_response(True, "Deletion record retrieved", history.to_dict())
```

## Data Retention Policy

### Recommended Policies:
1. **Indefinite Retention**: Keep all deletion records for legal compliance
2. **Time-based**: Delete records older than X years (e.g., 7 years for GDPR)
3. **Anonymization**: After X years, anonymize PII while keeping statistics

### Cleanup Script Example:
```python
from datetime import datetime, timedelta

def cleanup_old_deletion_history(years=7):
    """Anonymize deletion records older than specified years"""
    cutoff_date = datetime.utcnow() - timedelta(days=years*365)
    
    old_records = UserDeletionHistory.query.filter(
        UserDeletionHistory.account_deleted_at < cutoff_date
    ).all()
    
    for record in old_records:
        # Anonymize PII
        record.firstname = "REDACTED"
        record.lastname = "REDACTED"
        record.email = f"deleted_{record.id}@redacted.com"
        record.phone = "REDACTED"
        record.billing_first_name = "REDACTED"
        record.billing_last_name = "REDACTED"
        record.billing_email = "REDACTED"
        record.billing_phone = "REDACTED"
        record.billing_address = "REDACTED"
        record.ip_address = "0.0.0.0"
    
    db.session.commit()
    return len(old_records)
```

## Security Considerations

1. **Access Control**: Only admins should access deletion history
2. **PII Protection**: Implement proper access controls and encryption
3. **Audit Logging**: Log all access to deletion history
4. **GDPR Compliance**: Ensure compliance with right to be forgotten (consider anonymization)

## Testing

### Test Account Deletion Flow:
```python
def test_account_deletion_creates_history():
    # Create test user
    user = User(...)
    db.session.add(user)
    db.session.commit()
    
    user_id = user.id
    user_email = user.email
    
    # Delete account
    response = client.delete('/delete-account', 
                            headers={'Authorization': f'Bearer {token}'})
    
    assert response.status_code == 200
    
    # Verify user is deleted
    assert User.query.get(user_id) is None
    
    # Verify history exists
    history = UserDeletionHistory.query.filter_by(user_id=user_id).first()
    assert history is not None
    assert history.email == user_email
```

## Benefits

1. ✅ **Compliance**: Meet legal data retention requirements
2. ✅ **Audit Trail**: Complete record of account deletions
3. ✅ **Analytics**: Understand why users leave
4. ✅ **Support**: Handle post-deletion inquiries
5. ✅ **Recovery**: Potential to restore accounts if needed
6. ✅ **Business Intelligence**: Analyze churn patterns

## Future Enhancements

1. **Admin Dashboard**: Visual interface for viewing deletion history
2. **Export Functionality**: Export deletion records to CSV/Excel
3. **Automated Reports**: Weekly/monthly deletion summaries
4. **Restoration Feature**: Allow account restoration within X days
5. **Enhanced Metadata**: Capture more detailed deletion context
6. **Integration**: Connect with analytics platforms for churn analysis

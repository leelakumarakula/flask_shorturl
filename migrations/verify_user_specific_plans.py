"""
Test Script: Verify User-Specific Plan Implementation
Date: 2026-02-10

This script helps verify that the user-specific plan implementation is working correctly.
Run this after applying the database migration.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models.subscription import RazorpaySubscriptionPlan
from app.models.user import User
from sqlalchemy import text

def verify_schema():
    """Verify the database schema is correct"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("Schema Verification")
        print("=" * 60)
        
        try:
            # Check user_id column type
            result = db.session.execute(text("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'razorpay_subscription_plans' 
                AND column_name = 'user_id'
            """))
            
            row = result.fetchone()
            if row:
                print(f"\n✓ user_id column:")
                print(f"  - Type: {row[1]}")
                print(f"  - Nullable: {row[2]}")
                
                if row[1] == 'integer' and row[2] == 'NO':
                    print("  ✓ Schema is correct!")
                else:
                    print("  ✗ Schema needs migration")
                    return False
            else:
                print("✗ user_id column not found!")
                return False
            
            # Check for unique constraint
            result = db.session.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'razorpay_subscription_plans' 
                AND constraint_name = 'uq_user_plan'
            """))
            
            if result.fetchone():
                print("\n✓ Unique constraint 'uq_user_plan' exists")
            else:
                print("\n✗ Unique constraint 'uq_user_plan' not found")
                return False
            
            # Check for foreign key
            result = db.session.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'razorpay_subscription_plans' 
                AND constraint_type = 'FOREIGN KEY'
            """))
            
            if result.fetchone():
                print("✓ Foreign key constraint exists")
            else:
                print("✗ Foreign key constraint not found")
                return False
            
            return True
            
        except Exception as e:
            print(f"\n✗ Error verifying schema: {str(e)}")
            return False

def verify_data():
    """Verify existing data structure"""
    app = create_app()
    
    with app.app_context():
        print("\n" + "=" * 60)
        print("Data Verification")
        print("=" * 60)
        
        try:
            # Count total plans
            total_plans = RazorpaySubscriptionPlan.query.count()
            print(f"\n✓ Total plans in database: {total_plans}")
            
            # Count plans per user
            result = db.session.execute(text("""
                SELECT user_id, COUNT(*) as plan_count 
                FROM razorpay_subscription_plans 
                GROUP BY user_id
            """))
            
            print("\nPlans per user:")
            for row in result:
                user = User.query.get(row[0])
                user_email = user.email if user else "Unknown"
                print(f"  - User {row[0]} ({user_email}): {row[1]} plan(s)")
            
            # Check for duplicates (should be 0)
            result = db.session.execute(text("""
                SELECT user_id, plan_name, period, interval, COUNT(*) 
                FROM razorpay_subscription_plans 
                GROUP BY user_id, plan_name, period, interval 
                HAVING COUNT(*) > 1
            """))
            
            duplicates = result.fetchall()
            if duplicates:
                print(f"\n✗ Found {len(duplicates)} duplicate plans:")
                for dup in duplicates:
                    print(f"  - User {dup[0]}, Plan {dup[1]}, Period {dup[2]}, Count {dup[4]}")
            else:
                print("\n✓ No duplicate plans found (unique constraint working)")
            
            # Show sample plans
            sample_plans = RazorpaySubscriptionPlan.query.limit(5).all()
            if sample_plans:
                print("\nSample plans:")
                for plan in sample_plans:
                    user = User.query.get(plan.user_id)
                    user_email = user.email if user else "Unknown"
                    print(f"  - {plan.plan_name} ({plan.period}) - User: {user_email} - Razorpay ID: {plan.razorpay_plan_id}")
            
            return True
            
        except Exception as e:
            print(f"\n✗ Error verifying data: {str(e)}")
            return False

def main():
    """Run all verification tests"""
    print("\n" + "=" * 60)
    print("User-Specific Plan Implementation Verification")
    print("=" * 60)
    
    schema_ok = verify_schema()
    data_ok = verify_data()
    
    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)
    
    if schema_ok and data_ok:
        print("\n✓ All verifications passed!")
        print("\nThe user-specific plan implementation is working correctly.")
        print("\nNext steps:")
        print("1. Test creating a new subscription")
        print("2. Test renewing an existing subscription")
        print("3. Test upgrading/downgrading plans")
    else:
        print("\n✗ Some verifications failed")
        print("\nPlease:")
        print("1. Run the migration script if schema is incorrect")
        print("2. Check the error messages above for details")

if __name__ == '__main__':
    main()

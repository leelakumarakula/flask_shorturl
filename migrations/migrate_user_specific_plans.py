"""
Migration Helper: Update Razorpay Plans to User-Specific
Date: 2026-02-10

This script helps migrate the razorpay_subscription_plans table to support user-specific plans.

IMPORTANT: 
- Backup your database before running this migration
- This will clear existing plans (they will be recreated when users subscribe)
- Run during low traffic period
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from sqlalchemy import text

def run_migration():
    """Run the migration to convert to user-specific plans"""
    app = create_app()
    
    with app.app_context():
        try:
            print("=" * 60)
            print("Starting migration: User-Specific Razorpay Plans")
            print("=" * 60)
            
            # Step 1: Backup existing data (optional - print count)
            result = db.session.execute(text("SELECT COUNT(*) FROM razorpay_subscription_plans"))
            count = result.scalar()
            print(f"\n✓ Current plans in database: {count}")
            
            if count > 0:
                response = input(f"\n⚠️  This will delete {count} existing plans. Continue? (yes/no): ")
                if response.lower() != 'yes':
                    print("Migration cancelled.")
                    return
            
            # Step 2: Clear existing plans
            print("\n→ Clearing existing plans...")
            db.session.execute(text("TRUNCATE TABLE razorpay_subscription_plans"))
            db.session.commit()
            print("✓ Existing plans cleared")
            
            # Step 3: Drop old user_id column
            print("\n→ Dropping old user_id column...")
            try:
                db.session.execute(text("ALTER TABLE razorpay_subscription_plans DROP COLUMN user_id"))
                db.session.commit()
                print("✓ Old user_id column dropped")
            except Exception as e:
                print(f"⚠️  Column might already be dropped: {e}")
                db.session.rollback()
            
            # Step 4: Add new user_id column with foreign key
            print("\n→ Adding new user_id column with foreign key...")
            try:
                db.session.execute(text("""
                    ALTER TABLE razorpay_subscription_plans 
                    ADD COLUMN user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
                """))
                db.session.commit()
                print("✓ New user_id column added with foreign key")
            except Exception as e:
                print(f"⚠️  Column might already exist: {e}")
                db.session.rollback()
            
            # Step 5: Add unique constraint
            print("\n→ Adding unique constraint...")
            try:
                db.session.execute(text("""
                    ALTER TABLE razorpay_subscription_plans 
                    ADD CONSTRAINT uq_user_plan UNIQUE (user_id, plan_name, period, interval)
                """))
                db.session.commit()
                print("✓ Unique constraint added")
            except Exception as e:
                print(f"⚠️  Constraint might already exist: {e}")
                db.session.rollback()
            
            # Step 6: Verify changes
            print("\n→ Verifying schema changes...")
            result = db.session.execute(text("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'razorpay_subscription_plans' 
                AND column_name = 'user_id'
            """))
            
            for row in result:
                print(f"✓ Column: {row[0]}, Type: {row[1]}, Nullable: {row[2]}")
            
            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. User-specific plans will be created automatically when users subscribe")
            print("2. Renewals will reuse the existing user-specific plan ID")
            print("3. Each user gets their own Razorpay plan instance")
            
        except Exception as e:
            print(f"\n❌ Migration failed: {str(e)}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    run_migration()

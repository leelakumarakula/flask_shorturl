-- Simpler Migration: Update razorpay_subscription_plans for user-specific plans
-- Date: 2026-02-10
-- Description: This migration handles the conversion to user-specific plans

-- IMPORTANT: Run this migration when no active subscriptions are being processed

-- Step 1: Backup the existing table (recommended)
-- CREATE TABLE razorpay_subscription_plans_backup AS SELECT * FROM razorpay_subscription_plans;

-- Step 2: Drop existing plans (they will be recreated as user-specific when users subscribe)
-- This is the simplest approach - old global plans will be replaced with user-specific ones
TRUNCATE TABLE razorpay_subscription_plans;

-- Step 3: Modify the user_id column to be an integer foreign key
-- First, drop the column
ALTER TABLE razorpay_subscription_plans DROP COLUMN user_id;

-- Step 4: Add the new user_id column as integer with foreign key
ALTER TABLE razorpay_subscription_plans 
ADD COLUMN user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE;

-- Step 5: Add unique constraint to prevent duplicate plans per user
ALTER TABLE razorpay_subscription_plans 
ADD CONSTRAINT uq_user_plan UNIQUE (user_id, plan_name, period, interval);

-- Step 6: Verify the changes
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name = 'razorpay_subscription_plans';

-- Note: After this migration:
-- 1. All old plans are cleared
-- 2. New user-specific plans will be created automatically when users subscribe
-- 3. Each user will get their own Razorpay plan ID
-- 4. Renewals will reuse the existing user-specific plan ID

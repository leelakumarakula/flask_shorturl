-- Remove start_at and expire_by columns from subscriptions table
ALTER TABLE subscriptions DROP COLUMN start_at;
ALTER TABLE subscriptions DROP COLUMN expire_by;

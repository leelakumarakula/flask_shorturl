-- Make next_billing_date nullable in subscriptions table
ALTER TABLE subscriptions ALTER COLUMN next_billing_date DATETIME NULL;

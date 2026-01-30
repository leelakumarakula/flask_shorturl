-- Update Pro Plan Prices
UPDATE plans 
SET price_usd = 5.00, price_inr = 430 
WHERE name = 'Pro';

-- Update Premium Plan Prices
UPDATE plans 
SET price_usd = 15.00, price_inr = 1290 
WHERE name = 'Premium';

-- Add Usage Columns (If not already added)
-- Note: These run automatically via the migration script previously, 
-- New column for Editable Links usage (Run this!)
-- ALTER TABLE users ADD usage_editable_links INT NOT NULL DEFAULT 0;

-- New column for URL Plan Name (Run this!)
ALTER TABLE urls ADD plan_name VARCHAR(50);
-- ALTER TABLE users ADD usage_qrs INT NOT NULL DEFAULT 0;

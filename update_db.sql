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
-- but you can run them manually if needed.
-- ALTER TABLE users ADD usage_links INT NOT NULL DEFAULT 0;
-- ALTER TABLE users ADD usage_qrs INT NOT NULL DEFAULT 0;

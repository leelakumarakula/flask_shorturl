-- Update Pro and Premium plans with Razorpay details
-- Database: MSSQL (Transact-SQL)

-- Update Pro Plan
UPDATE plans
SET
    period = 'monthly',
    interval = 1,
    item = N'{"name": "pro plan - monthly", "amount": ' + CAST(CAST(price_inr  AS INT) AS NVARCHAR(20)) + N', "currency": "INR", "description": "Description for the pro plan"}',
    notes = NULL
WHERE name = 'Pro';

-- Update Premium Plan
UPDATE plans
SET
    period = 'monthly',
    interval = 1,
    item = N'{"name": "premium plan - monthly", "amount": ' + CAST(CAST(price_inr  AS INT) AS NVARCHAR(20)) + N', "currency": "INR", "description": "Description for the premium plan"}',
    notes = NULL
WHERE name = 'Premium';

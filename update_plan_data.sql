UPDATE plans
SET
    period = 'monthly',
    interval = 1,
    item = N'{"name": "BASIC", "amount": ' + CAST(CAST(price_inr * 100 AS INT) AS NVARCHAR(20)) + N', "currency": "INR", "description": "Description for the pro plan"}',
    notes = NULL
WHERE name = 'BASIC';

-- Update Premium Plan
UPDATE plans
SET
    period = 'monthly',
    interval = 1,
    item = N'{"name": "PRO", "amount": ' + CAST(CAST(price_inr * 100 AS INT) AS NVARCHAR(20)) + N', "currency": "INR", "description": "Description for the premium plan"}',
    notes = NULL
WHERE name = 'PRO';

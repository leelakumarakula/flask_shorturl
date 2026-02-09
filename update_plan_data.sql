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



UPDATE users 

SET custom_limits = '{

    "max_links": 6, 

    "max_qrs": 5, 

    "max_custom_links": 10,

    "max_qr_with_logo": 5,

    "max_editable_links": -1,

    "allow_qr_styling": true,

    "allow_analytics": true,

    "analytics_level": "basic",

	"show_individual_stats":1,

    "allow_api_access": true

}' 

WHERE email = 'test@yopmail.com';
 
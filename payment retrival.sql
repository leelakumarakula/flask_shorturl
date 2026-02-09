SELECT 
    u.id AS user_id,
    u.email,
    CONCAT(u.firstname, ' ', u.lastname) AS user_name,
    we.created_at AS payment_date,
    we.subscription_id AS razorpay_subscription_id,
    we.payment_id AS razorpay_payment_id,
    CAST(JSON_VALUE(we.payload, '$.payload.payment.entity.amount') AS FLOAT) / 100 AS amount,
    rsp.plan_name AS plan,
    s.subscription_status AS status
FROM 
    webhook_events we
INNER JOIN 
    users u ON we.user_id = u.id
LEFT JOIN 
    subscriptions s ON we.subscription_id = s.razorpay_subscription_id
LEFT JOIN 
    razorpay_subscription_plans rsp ON s.razorpay_plan_id = rsp.razorpay_plan_id
WHERE 
    we.event_type IN ('payment.captured', 'subscription.charged')
    AND we.processed = 1
ORDER BY 
    we.created_at DESC;

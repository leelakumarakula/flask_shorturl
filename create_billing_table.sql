CREATE TABLE billing_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),
    email VARCHAR(120) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    address TEXT,
    razorpay_plan_id VARCHAR(255),
    razorpay_subscription_id VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

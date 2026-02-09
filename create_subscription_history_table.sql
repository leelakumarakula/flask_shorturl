-- Create subscription_history table
CREATE TABLE IF NOT EXISTS subscription_history (
    id VARCHAR(36) PRIMARY KEY,
    subscription_id VARCHAR(255) NOT NULL,
    user_id INTEGER NOT NULL,
    razorpay_plan_id VARCHAR(255),
    plan_amount FLOAT DEFAULT 0.0,
    cancelled_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancelled_reason VARCHAR(255) DEFAULT 'User Requested',
    subscription_start_date DATETIME,
    subscription_end_date DATETIME,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    card_id VARCHAR(255),
    total_count INTEGER,
    notes TEXT,
    
    -- Indexes for better query performance
    INDEX idx_subscription_id (subscription_id),
    INDEX idx_user_id (user_id),
    INDEX idx_cancelled_date (cancelled_date)
);

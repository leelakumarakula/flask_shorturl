-- Create user_deletion_history table to store historical data of deleted user accounts
-- This table persists user information even after account deletion for audit and compliance purposes

CREATE TABLE IF NOT EXISTS user_deletion_history (
    id VARCHAR(36) PRIMARY KEY,
    
    -- User Information
    user_id INT NOT NULL,
    firstname VARCHAR(100) NOT NULL,
    lastname VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    organization VARCHAR(200),
    
    -- Account Dates
    account_created_at DATETIME NOT NULL,
    account_deleted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Subscription Information (Latest/Last Active)
    last_subscription_plan VARCHAR(100),
    last_subscription_date DATETIME,
    last_subscription_end_date DATETIME,
    last_subscription_amount FLOAT,
    razorpay_subscription_id VARCHAR(255),
    
    -- Billing Information (Latest)
    billing_first_name VARCHAR(100),
    billing_last_name VARCHAR(100),
    billing_email VARCHAR(120),
    billing_phone VARCHAR(20),
    billing_address TEXT,
    
    -- Usage Statistics (at time of deletion)
    total_links_created INT DEFAULT 0,
    total_qrs_created INT DEFAULT 0,
    total_clicks INT DEFAULT 0,
    
    -- Deletion Metadata
    deletion_reason VARCHAR(255),
    deleted_by VARCHAR(50) DEFAULT 'user',
    ip_address VARCHAR(50),
    
    -- Additional metadata (JSON format for flexibility)
    additional_metadata TEXT,
    
    -- Indexes for efficient querying
    INDEX idx_user_id (user_id),
    INDEX idx_email (email),
    INDEX idx_account_deleted_at (account_deleted_at),
    INDEX idx_deleted_by (deleted_by)
);

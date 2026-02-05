IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='billing_info' AND xtype='U')
CREATE TABLE billing_info (
    id INT IDENTITY(1,1) PRIMARY KEY,
    user_id INT NOT NULL,
    first_name NVARCHAR(100) NOT NULL,
    last_name NVARCHAR(100),
    email NVARCHAR(120) NOT NULL,
    phone_number NVARCHAR(20) NOT NULL,
    address NVARCHAR(MAX),
    razorpay_plan_id NVARCHAR(255),
    razorpay_subscription_id NVARCHAR(255),
    amount FLOAT DEFAULT 0.0,
    plan_id INT,
    created_at DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

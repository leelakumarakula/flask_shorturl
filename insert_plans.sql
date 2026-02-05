-- Insert Free Plan
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level)
VALUES ('Free', 0, 0, 5, 2, 2, 0, 0, 0, 0, 0, 0, 'none');

-- Insert Pro Plan (Example Prices: $9.99 / ₹999 - Change as needed)
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level)
VALUES ('Pro', 9.99, 999, 250, 150, 50, 50, 50, 1, 1, 1, 0, 'basic');

-- Insert Premium Plan (Example Prices: $29.99 / ₹2999 - Change as needed)
-- Note: Set max_custom_links to 1000 (assumed typo in 10) and max_editable_links to -1 for unlimited
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level)
VALUES ('Premium', 29.99, 2999, 1000, 500, 1000, 50, -1, 1, 1, 1, 1, 'detailed');

-- Insert Pro Yearly Plan
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level, period, interval, item, notes)
VALUES ('Pro Yearly', 299.99, 24000, 50, 10, 10, 5, 5, 1, 1, 1, 1, 'basic', 'yearly', 1, '{"name": "Pro Yearly", "amount": 2400000, "currency": "INR", "description": "Yearly Pro Subscription"}', '{"type": "yearly_plan"}');

-- Insert Premium Yearly Plan
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level, period, interval, item, notes)
VALUES ('Premium Yearly', 899.99, 72000, 500, 100, 100, 50, 50, 1, 1, 1, 1, 'detailed', 'yearly', 1, '{"name": "Premium Yearly", "amount": 7200000, "currency": "INR", "description": "Yearly Premium Subscription"}', '{"type": "yearly_plan"}');
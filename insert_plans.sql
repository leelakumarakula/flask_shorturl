- Insert Free Plan
-- Insert Free Plan
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level)
VALUES ('FREE', 0, 0, 2, 2, 1, 0, 0, 0, 0, 0, 0, 'none');

-- Insert Pro Plan (Example Prices: $9.99 / ₹999 - Change as needed)
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level)
VALUES ('BASIC', 33.17, 2999, 50, 50, 20, 10, 10, 1, 1, 1, 0, 'basic');

-- Insert Premium Plan (Example Prices: $29.99 / ₹2999 - Change as needed)
-- Note: Set max_custom_links to 1000 (assumed typo in 10) and max_editable_links to -1 for unlimited
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level)
VALUES ('PRO', 88.46, 7999, 200, 200, 100, 50, -1, 1, 1, 1, 1, 'detailed');

-- Insert Pro Yearly Plan
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level, period, interval, item, notes)
VALUES ('BASIC YEARLY', 265.38, 24000, 50, 50, 20, 10, 10, 1, 1, 1, 0, 'basic', 'yearly', 1, '{"name": "BASIC YEARLY", "amount": 2400000, "currency": "INR", "description": "Yearly Pro Subscription"}', '{"type": "yearly_plan"}');

-- Insert Premium Yearly Plan
INSERT INTO plans (name, price_usd, price_inr, max_links, max_qrs, max_custom_links, max_qr_with_logo, max_editable_links, allow_qr_styling, allow_analytics, show_individual_stats, allow_api_access, analytics_level, period, interval, item, notes)
VALUES ('PRO YEARLY', 796.15, 72000, 200, 200, 100, 50, -1, 1, 1, 1, 1, 'detailed', 'yearly', 1, '{"name": "PRO YEARLY", "amount": 7200000, "currency": "INR", "description": "Yearly Premium Subscription"}', '{"type": "yearly_plan"}');


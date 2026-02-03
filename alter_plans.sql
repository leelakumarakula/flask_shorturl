-- Add columns for Razorpay plan integration
-- Database: MSSQL (Transact-SQL)

ALTER TABLE plans ADD period NVARCHAR(50);
ALTER TABLE plans ADD interval INT;
ALTER TABLE plans ADD item NVARCHAR(MAX); -- Using NVARCHAR(MAX) for JSON content
ALTER TABLE plans ADD notes NVARCHAR(MAX); -- Using NVARCHAR(MAX) for JSON content

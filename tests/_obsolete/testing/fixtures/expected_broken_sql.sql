-- elspais: expected-broken-links 2
-- Test fixture with SQL-style comment marker.
--
-- This file intentionally references mock requirement IDs that don't exist
-- in the actual spec files, to test the expected-broken-links feature with
-- SQL-style comments.

-- Validates: REQ-sqlmock001
SELECT * FROM test_first;

-- Validates: REQ-sqlmock002
SELECT * FROM test_second;

-- This one should NOT be suppressed (3rd ref, but marker only covers 2)
-- Validates: REQ-sqlmock003
SELECT * FROM test_third_should_warn;

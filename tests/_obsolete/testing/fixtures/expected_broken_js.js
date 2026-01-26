// elspais: expected-broken-links 2
/**
 * Test fixture with JavaScript-style comment marker.
 *
 * This file intentionally references mock requirement IDs that don't exist
 * in the actual spec files, to test the expected-broken-links feature with
 * JavaScript-style comments.
 */

function test_first_mock() {
    // Validates: REQ-jsmock001
    console.log("First test");
}

function test_second_mock() {
    // Validates: REQ-jsmock002
    console.log("Second test");
}

// This one should NOT be suppressed (3rd ref, but marker only covers 2)
function test_third_not_suppressed() {
    // Validates: REQ-jsmock003
    console.log("Third test - should warn");
}

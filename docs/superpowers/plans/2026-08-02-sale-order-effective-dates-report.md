# 2026-08-02: Sale Order Effective Dates — Implementation Report

## Task 1: Fix _KNOWN_GAPS contract test bug

### Step 3 Result (Confirm bug exists)
**Status: FAIL as expected** — Test `test_known_gaps_catches_entry_when_real_field_now_exists` failed with `DID NOT RAISE AssertionError`, proving the original logic did not catch the scenario where a gap has been fixed (field now exists in reality) but `_KNOWN_GAPS` entry was not removed.

### Step 5 Result (Both tests PASS)
**Status: PASS** — Both tests pass:
- `test_known_gaps_catches_entry_when_real_field_now_exists`: PASS (newly added test now catches the gap closure scenario)
- `test_gather_cases_fixture_labels_match_real_tool_fields`: PASS (existing test still works without regression)

### Commit
```
7fea52f fix(gather-cases-contract-test): _KNOWN_GAPS phải kiểm field thật ngay cả khi mục đã có ngoại lệ — bản gốc chỉ bắt 1/2 kịch bản cấu hình chết
```

### Summary
✅ Task 1 completed successfully. The contract test now properly validates that `_KNOWN_GAPS` entries must have both their labels still matching fixture text AND their fields still missing from real tools. This prevents dead configuration from accumulating.

### Round 1 fix (after review): Code brief recursion bug
**Note**: Code in brief Step 2, if copied verbatim, would cause `RecursionError` when `monkeypatch.setitem(globals(), "_real_fields_for_tool", _fake_real_fields)` redirects the name to the new function, and then `_fake_real_fields` calls `_real_fields_for_tool(tool_name)` for fallback on non-`get_sale_order_detail` tools — this lookup now finds the patched `_fake_real_fields` again, causing infinite recursion. **Fixed**: Captured the original reference BEFORE patching (`_original_real_fields_for_tool = _real_fields_for_tool`), so fallback calls use the real function. This is the correct solution; Step 3 result (FAIL with `DID NOT RAISE`) is as expected only because the fix was already applied before running tests.

---

**Full detail**: See `.superpowers/sdd/2026-08-02-sale-order-effective-dates/task-1-report.md`

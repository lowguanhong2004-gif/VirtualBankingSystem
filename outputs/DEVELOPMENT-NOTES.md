# Prototype debugging evidence

This is an AI-assisted development record. It describes issues actually encountered during implementation and validation, not a claim that the student discovered or fixed them independently.

| Observed issue | Cause and change | Evidence |
|---|---|---|
| Non-ASCII OTP could raise a Python `TypeError` | `hmac.compare_digest` on strings requires ASCII. Validate six ASCII digits first; malformed codes now follow the normal rejection and attempt-count path. | `test_non_ascii_and_malformed_otps_are_rejected_without_crash`; `test_unicode_otp_shows_error_instead_of_exception` |
| OTP could expire while waiting for a data lock | Verification initially checked expiry only before acquiring the lock. Recheck the real clock after acquiring it and before updating balances. | `test_otp_expiring_while_waiting_for_lock_cannot_commit` |
| Concurrent writes intermittently reported Windows access denied | Lock creation can encounter a lock file during deletion. Retry both file-exists and access-denied contention within the existing three-second limit. | Final `test_concurrent_deposits_keep_all_updates` passes; earlier failing trace retained in working logs |
| Disabled transaction fields could display a stale amount on a rerun | Rendering another set of fields while an OTP is pending caused misleading form values. Show the pending transaction summary and OTP controls; render entry forms again after completion or cancellation. | Final transfer and cancellation UI tests pass; live OTP captures show the pending amount directly |
| Local preview could not start with a custom port | The workspace package path made Streamlit infer development mode. The local launcher explicitly disables development mode. | Separate local previews successfully served on ports 8501 and 8502 |

Banking invariants verified by the tests: no balance changes before OTP confirmation; invalid or expired codes do not complete transactions; replaying a completed request cannot charge again; current balance is revalidated at commit; transfers preserve total account funds; failed JSON writes leave the existing account data unchanged.

The source tests and exact results are included with the prototype. Use your own testing and explanations for the assessed report.

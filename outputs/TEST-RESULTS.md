# Verification results

Executed on 13 September 2026 with Python 3.12 and Streamlit 1.63.0 against disposable JSON files. This is machine-generated verification evidence, not student-authored report text.

Latest session UI update: all **28 tests (17 logic and 11 UI)** passed in 22.025 seconds, exit code 0. The sidebar shows a live inactivity countdown, progress bar, expiry warning and Stay signed in button, with five-minute default and 30-second demo durations. Tests verify renewal by navigation and Stay signed in, no renewal from automatic reruns or OTP expiry, clearing the pending transaction and authentication on timeout, restoration of the default after login, and rejection of attempts to revive an expired session by renewal or selecting a longer duration. Unsubmitted form typing is not sent to the server and does not renew the timer.

Latest OTP update: all **23 tests (17 logic and 6 UI)** passed in 14.421 seconds, exit code 0. Every service uses a shared countdown and progress bar that refresh every second without refreshing the input form. UI checks cover the displayed remaining time, countdown reset on retry, removal of the confirmation form on expiry, and countdown availability for all four services. Incorrect entries replace the code with a different six-digit OTP and restart its 60-second validity. Regression checks cover rejection of previously issued codes, expiry at the replacement code's exact deadline, avoidance of repeated random codes, immediate display of the replacement, clearing the input, unchanged balances on failure, and successful confirmation with the latest code. The three-attempt limit remains enforced. The results and browser captures below document the earlier prototype; the walkthrough predates automatic OTP replacement on retries and the live countdown.

The 14 logic tests cover valid/invalid login, salted hashes, three-failure locking and lock expiry, amount and payment-detail validation, wrong/expired OTPs, three-attempt OTP limits, malformed and non-ASCII OTP input, expiry while waiting for the write lock, ownership, duplicate confirmation, transfer conservation and both histories, restart persistence, all payment types, card masking, CSV contents, concurrent deposits, unreadable JSON preservation and failed-write behavior.

The five UI tests cover valid/invalid login and logout, navigation, insufficient funds, transfer and recipient balances, wrong/correct and non-ASCII OTP interactions, bill/card/deposit confirmations, history rendering, chart rendering, cancellation, simulated OTP expiry and simulated session inactivity timeout. UI expiry and timeout use test-controlled state; they do not establish elapsed wall-clock behavior in a disconnected browser.

Independent real-browser check: Alice started at RM 5,000.00; an incorrect OTP returned an error and preserved the balance. The correct OTP then completed one RM 100.00 transfer to Bob and displayed RM 4,900.00. Browser screenshots are included in `screenshots/`. Current persisted demo data retains that transfer.

The portable test sources are in `tests/test_bank.py` and `tests/test_ui.py` in the outputs directory. Tests do not edit the supplied demo account data. After installing requirements, run `python -m unittest discover -s tests -v` from that directory to reproduce the automated cases.

These checks verify the prototype; they do not prove the report, recorded demonstration, official disclosure form, student authorship or submission is complete.

## Banking logic

Live session UI verification used separate disposable accounts and the 30-second demo. The warning appeared with four seconds remaining; Stay signed in reset the countdown (28 seconds at the next observation) and cleared the warning. Without further input or refresh, the login form and automatic-logout explanation appeared, observed 37.363 seconds after renewal. This is an observation after the deadline rather than an exact timing measurement. See `evidence/session-ui.json`.

Live countdown verification used a separate local preview and disposable accounts. The display decreased from 58 to 45 seconds over 13.491 seconds while retaining typed input. An incorrect submission generated a different code and reset the display to 58 seconds at observation. With no further click or refresh, the confirmation form disappeared after the replacement deadline; Alice retained RM 5,000.00 and zero completed activities. The observation after expiry was 66.679 seconds after the replacement snapshot, not the exact expiry instant. See `evidence/otp-countdown.json`.

Exit code: 0

```text
test_all_services_and_csv (__main__.BankTests.test_all_services_and_csv) ... ok
test_balance_rechecked_at_confirmation (__main__.BankTests.test_balance_rechecked_at_confirmation) ... ok
test_concurrent_deposits_keep_all_updates (__main__.BankTests.test_concurrent_deposits_keep_all_updates) ... ok
test_corrupt_data_preserved (__main__.BankTests.test_corrupt_data_preserved) ... ok
test_expiry_at_exact_boundary (__main__.BankTests.test_expiry_at_exact_boundary) ... ok
test_failed_write_does_not_commit (__main__.BankTests.test_failed_write_does_not_commit) ... ok
test_invalid_amounts_and_details (__main__.BankTests.test_invalid_amounts_and_details) ... ok
test_login_hashes_and_lock_expiry (__main__.BankTests.test_login_hashes_and_lock_expiry) ... ok
test_non_ascii_and_malformed_otps_are_rejected_without_crash (__main__.BankTests.test_non_ascii_and_malformed_otps_are_rejected_without_crash) ... ok
test_one_use_even_with_copied_request (__main__.BankTests.test_one_use_even_with_copied_request) ... ok
test_otp_expiring_while_waiting_for_lock_cannot_commit (__main__.BankTests.test_otp_expiring_while_waiting_for_lock_cannot_commit) ... ok
test_transfer_balance_history_and_restart (__main__.BankTests.test_transfer_balance_history_and_restart) ... ok
test_wrong_otp_and_three_attempt_limit (__main__.BankTests.test_wrong_otp_and_three_attempt_limit) ... ok
test_wrong_user_cannot_confirm (__main__.BankTests.test_wrong_user_cannot_confirm) ... ok
Ran 14 tests in 5.374s
OK
```

## Streamlit UI

Exit code: 0

```text
test_bill_card_deposit_and_charts (__main__.UITests.test_bill_card_deposit_and_charts) ... 2026-09-13 18:36:21.465 DEBUG   streamlit.components.v2.manifest_scanner: Filtered 70 packages down to 1 candidates for component scanning
test_login_errors_and_logout (__main__.UITests.test_login_errors_and_logout) ... 2026-09-13 18:36:23.908 DEBUG   streamlit.components.v2.manifest_scanner: Filtered 70 packages down to 1 candidates for component scanning
test_transfer_wrong_otp_then_success_and_recipient (__main__.UITests.test_transfer_wrong_otp_then_success_and_recipient) ... 2026-09-13 18:36:24.846 DEBUG   streamlit.components.v2.manifest_scanner: Filtered 70 packages down to 1 candidates for component scanning
test_unicode_otp_shows_error_instead_of_exception (__main__.UITests.test_unicode_otp_shows_error_instead_of_exception) ... 2026-09-13 18:36:26.149 DEBUG   streamlit.components.v2.manifest_scanner: Filtered 70 packages down to 1 candidates for component scanning
test_validation_cancel_expiry_and_timeout (__main__.UITests.test_validation_cancel_expiry_and_timeout) ... 2026-09-13 18:36:27.163 DEBUG   streamlit.components.v2.manifest_scanner: Filtered 70 packages down to 1 candidates for component scanning
Ran 5 tests in 6.876s
OK
```

## Additional live browser evidence

- A separate disposable dataset completed exactly four activities: RM 100 transfer to Bob, RM 12.50 electricity bill, RM 20 credit card payment and RM 30 deposit. Alice finished at RM 4,897.50; Bob finished at RM 2,600.00. The full ledger and account CSV are included under `evidence/`.
- A request expired after more than 60 seconds of real elapsed time and did not move money.
- Three incorrect passwords locked Charlie's account; a correct password was rejected during the lock and accepted after it expired.
- An idle, connected Bob session automatically returned to the login page after the five-minute interval, without a user interaction. The saved start and timeout-observation timestamps are in `evidence/session-timeout.json`; the saved observation was recorded after 321.496 seconds. This is an observation after the deadline, not a measurement of the exact instant of logout. It establishes connected-browser behavior in this test, not behavior while the browser is disconnected.
- The separate server was actually stopped and restarted. Alice's RM 4,897.50 balance and all four activities were visible after logging in again.
- `Virtual-Banking-Walkthrough.mp4` is a 142-second captioned sequence of live browser captures. Full decoding passed with no errors; every scene was sampled for visual QA. Resolution: 1280 x 800; frame rate: 25 fps. It is a learning walkthrough rather than the student's recorded assessment demonstration.

The default `data/bank.json` is a separate dataset containing the earlier RM 100 verification transfer and subsequent local demo activity. Additional isolated live testing did not add transactions to it. Screenshots 08-21 and the walkthrough use the disposable dataset. Screenshots 02-04 have been refreshed with clean captures of the final interface.

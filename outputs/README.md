# Virtual Banking System prototype

This is an AI-assisted learning prototype for Project 1 of BMCS2713. It is a local simulation, with no real bank, card processor, cash collection or SMS/email service. Review the code, understand each function and follow your lecturer's rules before using any part in assessed work. The assignment explicitly prohibits AI-generated report text and requires independent work, an originality declaration and an AI Usage Disclosure Form. This README is run guidance, not a submission report.

## Run on this computer

Open PowerShell in this folder and run:

```powershell
.\Start-Banking.ps1
```

Open http://127.0.0.1:8501 in your browser. Stop the server with Ctrl+C in the terminal that started it. If the preview is already running, use its browser page instead of starting a second instance on the same port.

## Run on another computer

Install Python 3.12, then open a terminal in the folder containing `app.py`:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1
```

The `.py` file contains both the banking logic and interface. It creates `data/bank.json` automatically, so a separate initial data file is not required. Keep `requirements.txt` for installation. The PowerShell launcher uses the local runtime when available and is not required on another computer.

## Demo accounts

| Username | Password | Initial balance |
|---|---|---:|
| alice | DemoBank123! | RM 5,000.00 |
| bob | DemoBank123! | RM 2,500.00 |
| charlie | DemoBank123! | RM 1,500.00 |

The included JSON contains transactions from local demo use, including the first browser verification transfer of RM 100 from Alice to Bob. The table above gives fresh-account starting balances; check the dashboard for current balances. The app preserves subsequent changes across restarts. To make a fresh demo, first stop every server using this data, keep a backup of the data folder, and run a copied `app.py` in a new folder with no existing data.

## Transaction workflow

1. Log in and choose **Payments & deposits**.
2. Select a service tab, enter the details and request an OTP.
3. Confirm the displayed transaction details. The simulated OTP is shown in the application and expires after 60 seconds. Balances have not changed at this point.
4. Enter the OTP and confirm once. A successful transaction updates balances and writes one transaction record atomically to JSON.
5. Open **Transaction history**, filter by credit/debit and download a CSV if required. Transfers appear in both users' histories, with the balance after that transfer.

Wrong OTPs leave the balances unchanged. Three wrong OTPs close that request; expiry also requires a new request. Cancelling, logging out or timing out discards an unconfirmed request. Completed transaction IDs prevent duplicate charges even if a request is replayed.

## Implemented enhancements

- JSON persistence with a file lock and atomic writes.
- Unique password salts and PBKDF2-HMAC-SHA256 hashing with 200,000 iterations.
- Account lock for 60 seconds after three failed logins, persisted across restarts.
- Five-minute inactivity logout, checked by a background Streamlit fragment every five seconds while the browser session remains connected. It is also checked on the next interaction.
- 60-second OTP expiry, fresh six-digit codes for new requests and a three-attempt limit.
- Account balance and spending charts.
- CSV export and credit/debit filters.

Amounts are integer cents; inputs must be positive, finite and have no more than two decimal places. The simulation caps each transaction at RM 1,000,000. Bill references contain 4-20 digits. Credit card payment accepts fictional 16-digit numbers; it does not verify issuer validity or contact a real processor. Only the last four card digits are retained in transaction history.

## Code map

| Function/class | Purpose |
|---|---|
| `amount_cents` | Validate amounts without rounding or floating-point balance arithmetic |
| `password_hash` / `initial_data` | Create salted hashes and fictional starting accounts |
| `BankStore.lock/load/save` | Serialize writes and preserve JSON data safely |
| `BankStore.authenticate` | Check login credentials and manage account locks |
| `BankStore.validate/prepare` | Validate transaction details and create an OTP request |
| `BankStore.confirm` | Verify request ownership, expiry, OTP, duplicate ID and current balance; commit once |
| `user_history` / `export_csv` | Build account-specific histories and downloadable CSV data |
| `main` | Render Streamlit pages, session state, watchdog, forms and receipts |

## Verification and limits

See `TEST-RESULTS.md` for automated results and `screenshots/` for real browser captures. Automated UI tests verify rendered elements and interactions; they do not measure mobile appearance or prove inactivity timing in a disconnected browser. A browser check independently confirmed that a wrong OTP preserved Alice's balance and that a correct OTP completed the RM 100 transfer.

This prototype uses known demo credentials and displays OTPs in the same browser. It is not a production authentication or OTP delivery system. JSON storage is suitable for this small local simulation; a database, secure credential management and independent OTP delivery would be needed for a deployed system. A crash while holding the file lock may leave a `.lock` file. Before removing such a file, stop all processes using this bank and verify no transaction is running; the app never removes a lock automatically.

## Portable tests and walkthrough

After installing requirements, run the packaged tests from this folder:

```powershell
python -m unittest discover -s tests -v
```

The 19 cases use temporary accounts and do not modify `data/bank.json`. `TEST-RESULTS.md` contains the actual result of running the packaged tests.

`Virtual-Banking-Walkthrough.mp4` is a captioned sequence of live browser captures, edited to hold each state long enough to read. It is a learning walkthrough, with no narration or continuous capture of every mouse movement. It is not presented as your own recorded assessment demonstration. Captures use a separate disposable dataset: Alice finishes at RM 4,897.50 after a RM 100 transfer, RM 12.50 bill payment, RM 20 credit card payment and RM 30 deposit; Bob finishes at RM 2,600.00. These additional tests do not change the default demo data described above. The corresponding ledger and CSV are saved under `evidence/`.

The assessed PDF report, your own explanation and recorded demonstration, and the official AI disclosure form are still outstanding. Do not claim those are completed based on this prototype.

Official implementation references: [Streamlit rerun](https://docs.streamlit.io/develop/api-reference/execution-flow/st.rerun), [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).

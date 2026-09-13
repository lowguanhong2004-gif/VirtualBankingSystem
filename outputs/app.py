"""Virtual Banking System learning prototype. Run: streamlit run app.py.

AI-assisted code: review, understand and adapt it before any assessed use.
All accounts, payments and OTP delivery are simulated.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import tempfile
import time
import uuid

OTP_SECONDS = 60
LOCK_SECONDS = 60
SESSION_SECONDS = 300
MAX_CENTS = 100_000_000
BILL_SERVICES = ("Electricity", "Water", "Internet", "Mobile phone")
DEMO_ACCOUNTS = {"alice": ("Alice Tan", 500000), "bob": ("Bob Lee", 250000),
                 "charlie": ("Charlie Lim", 150000)}


class BankError(ValueError):
    """An expected validation error suitable for displaying to the user."""


def money(cents):
    return f"RM {cents / 100:,.2f}"


def amount_cents(value):
    """Reject rather than silently round invalid amounts. Store integer cents."""
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount <= 0:
            raise BankError("Enter an amount greater than RM 0.00.")
        if amount > Decimal(MAX_CENTS) / 100:
            raise BankError("The maximum amount per transaction is RM 1,000,000.00.")
        cents = amount * 100
        if cents != cents.to_integral_value():
            raise BankError("Use no more than two decimal places.")
        return int(cents)
    except (InvalidOperation, TypeError):
        raise BankError("Enter a valid number, for example 25.50.") from None


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200000).hex()


def initial_data():
    users = {}
    for username, (name, balance) in DEMO_ACCOUNTS.items():
        salt = secrets.token_hex(16)
        users[username] = {"name": name, "salt": salt,
                           "password_hash": password_hash("DemoBank123!", salt),
                           "balance_cents": balance, "opening_cents": balance,
                           "failed_logins": 0, "locked_until": 0}
    return {"version": 1, "users": users, "transactions": []}


class BankStore:
    """JSON persistence with a cross-process lock and atomic file replacement."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock():
            if not self.path.exists():
                self.save(initial_data())
            self.load()

    @contextmanager
    def lock(self):
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        deadline = time.monotonic() + 3
        while True:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except (FileExistsError, PermissionError):
                # Windows can briefly report access denied while a lock file is
                # being deleted by another session. Treat this as bounded contention.
                if time.monotonic() >= deadline:
                    raise BankError("The data lock is busy or inaccessible. Try again shortly.") from None
                time.sleep(0.025)
        try:
            os.write(descriptor, str(os.getpid()).encode())
            yield
        finally:
            os.close(descriptor)
            lock_path.unlink()

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data["version"] != 1 or not isinstance(data["transactions"], list):
                raise ValueError("Unsupported data structure")
            for user in data["users"].values():
                for field in ("balance_cents", "opening_cents", "failed_logins"):
                    if type(user[field]) is not int or user[field] < 0:
                        raise ValueError("Invalid account values")
                bytes.fromhex(user["salt"])
                bytes.fromhex(user["password_hash"])
                float(user["locked_until"])
                str(user["name"])
            return data
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise BankError("Cannot read the bank data. Restore a valid backup; existing data was preserved.") from None

    def save(self, data):
        """Caller holds the lock; a failed write preserves the previous file."""
        descriptor, filename = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(data, output, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(filename, self.path)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def authenticate(self, username, password, now=None):
        now = time.time() if now is None else now
        username = username.strip().lower()
        with self.lock():
            data = self.load()
            user = data["users"].get(username)
            if user is None:
                # Perform comparable hash work for unknown users.
                password_hash(password, "00" * 16)
                raise BankError("Invalid username or password.")
            if user["locked_until"] > now:
                remaining = max(1, int(user["locked_until"] - now + 0.999))
                raise BankError(f"Account locked. Try again in {remaining} seconds.")
            if user["locked_until"]:
                user["failed_logins"] = 0
                user["locked_until"] = 0
            valid = hmac.compare_digest(password_hash(password, user["salt"]), user["password_hash"])
            if not valid:
                user["failed_logins"] += 1
                if user["failed_logins"] >= 3:
                    user["locked_until"] = now + LOCK_SECONDS
                self.save(data)
                if user["failed_logins"] >= 3:
                    raise BankError("Three failed logins. Account locked for 60 seconds.")
                raise BankError("Invalid username or password.")
            user["failed_logins"] = 0
            user["locked_until"] = 0
            self.save(data)
            return username

    def validate(self, data, username, kind, cents, target):
        if username not in data["users"]:
            raise BankError("Please log in again.")
        if kind not in ("Transfer", "Bill payment", "Credit card payment", "Deposit"):
            raise BankError("Unknown transaction type.")
        if type(cents) is not int or not 0 < cents <= MAX_CENTS:
            raise BankError("Invalid transaction amount.")
        user = data["users"][username]
        if kind != "Deposit" and cents > user["balance_cents"]:
            raise BankError(f"Insufficient balance. Your balance is {money(user['balance_cents'])}.")
        if kind == "Transfer":
            if target == username:
                raise BankError("You cannot transfer money to yourself.")
            if target not in data["users"]:
                raise BankError("The recipient does not exist.")
        if kind == "Bill payment":
            parts = target.split(":", 1)
            if len(parts) != 2 or parts[0] not in BILL_SERVICES or not parts[1].isdigit() or not 4 <= len(parts[1]) <= 20:
                raise BankError("Select a service and enter a bill reference of 4-20 digits.")
        if kind == "Credit card payment" and (not target.isdigit() or len(target) != 16):
            raise BankError("Enter a fictional 16-digit credit card number.")
        if kind == "Deposit" and target != "Simulated cash deposit":
            raise BankError("Invalid deposit source.")

    def prepare(self, username, kind, amount, target, now=None):
        cents = amount_cents(amount)
        target = target.strip()
        self.validate(self.load(), username, kind, cents, target)
        now = time.time() if now is None else now
        return {"id": uuid.uuid4().hex, "user": username, "kind": kind, "cents": cents,
                "target": target, "otp": f"{secrets.randbelow(1000000):06d}",
                "expires_at": now + OTP_SECONDS, "attempts": 0, "closed": False}

    def confirm(self, username, pending, otp, now=None):
        live_clock = now is None
        now = time.time() if now is None else now
        if pending["user"] != username or pending["closed"]:
            raise BankError("This transaction is no longer available. Start a new transaction.")
        if now >= pending["expires_at"]:
            pending["closed"] = True
            raise BankError("OTP expired. Start a new transaction to receive another OTP.")
        entered = str(otp).strip()
        valid_format = len(entered) == 6 and entered.isascii() and entered.isdigit()
        if not valid_format or not hmac.compare_digest(entered, pending["otp"]):
            pending["attempts"] += 1
            if pending["attempts"] >= 3:
                pending["closed"] = True
                raise BankError("Three incorrect OTP attempts. Start a new transaction.")
            raise BankError(f"Incorrect OTP. {3 - pending['attempts']} attempts remaining.")
        with self.lock():
            # A request may expire while waiting for another session's write lock.
            if live_clock and time.time() >= pending["expires_at"]:
                pending["closed"] = True
                raise BankError("OTP expired. Start a new transaction to receive another OTP.")
            data = self.load()
            if any(row["id"] == pending["id"] for row in data["transactions"]):
                pending["closed"] = True
                raise BankError("This transaction has already been completed.")
            # Balances may have changed in another browser session since preparation.
            self.validate(data, username, pending["kind"], pending["cents"], pending["target"])
            cents, kind, target = pending["cents"], pending["kind"], pending["target"]
            user = data["users"][username]
            user["balance_cents"] += cents if kind == "Deposit" else -cents
            recipient_balance = None
            if kind == "Transfer":
                recipient = data["users"][target]
                recipient["balance_cents"] += cents
                recipient_balance = recipient["balance_cents"]
            displayed_target = "Card ending " + target[-4:] if kind == "Credit card payment" else target
            row = {"id": pending["id"], "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
                   "kind": kind, "user": username, "target": displayed_target, "amount_cents": cents,
                   "balance_cents": user["balance_cents"], "recipient_balance_cents": recipient_balance,
                   "status": "Completed"}
            data["transactions"].append(row)
            self.save(data)
            pending["closed"] = True
            return row


def user_history(data, username):
    rows = []
    for row in data["transactions"]:
        incoming = row["kind"] == "Transfer" and row["target"] == username
        if row["user"] != username and not incoming:
            continue
        credit = incoming or row["kind"] == "Deposit"
        rows.append({"Transaction ID": row["id"], "Date / time (UTC)": row["timestamp"],
                     "Type": "Transfer received" if incoming else row["kind"],
                     "Details": row["user"] if incoming else row["target"],
                     "Amount (RM)": f"{row['amount_cents'] / 100:.2f}",
                     "Direction": "Credit" if credit else "Debit", "Status": row["status"],
                     "Balance (RM)": f"{(row['recipient_balance_cents'] if incoming else row['balance_cents']) / 100:.2f}"})
    return rows


def export_csv(rows):
    output = io.StringIO(newline="")
    columns = ["Transaction ID", "Date / time (UTC)", "Type", "Details", "Amount (RM)", "Direction", "Status", "Balance (RM)"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
                         for key, value in row.items()})
    return output.getvalue().encode("utf-8-sig")


def main():
    import streamlit as st
    import pandas as pd

    st.set_page_config(page_title="Vela | Virtual Banking", page_icon="🏦", layout="wide")
    st.markdown("""<style>
      .stApp {background: #f5f7fb;}
      h1,h2,h3 {color: #162b45;}
      [data-testid="stSidebar"] {background: #e6edf5;}
      [data-testid="stMetric"] {background: white; padding: 1.2rem; border-radius: 12px; border: 1px solid #dce3ec;}
      .block-container {max-width: 1250px; padding-top: 2rem;}
    </style>""", unsafe_allow_html=True)
    st.title("Vela Virtual Banking")
    st.caption("A Python + Streamlit banking simulation · All money and accounts are fictional")
    try:
        store = BankStore(os.environ.get("VIRTUAL_BANK_DATA", str(Path(__file__).parent / "data" / "bank.json")))
    except (BankError, OSError) as error:
        st.error(str(error))
        st.stop()

    def sign_out(message):
        st.session_state.clear()
        st.session_state["notice"] = message

    now = time.time()
    if st.session_state.get("user") and now - st.session_state.get("last_activity", now) >= SESSION_SECONDS:
        sign_out("Your session expired after five minutes of inactivity. Please log in again.")
    if "notice" in st.session_state:
        st.info(st.session_state.pop("notice"))
    if not st.session_state.get("user"):
        left, right = st.columns([1, 1])
        with left:
            st.subheader("Welcome back")
            with st.form("login"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Log in", type="primary")
            if submitted:
                try:
                    st.session_state["user"] = store.authenticate(username, password)
                    st.session_state["last_activity"] = time.time()
                    st.rerun()
                except (BankError, OSError) as error:
                    st.error(str(error))
        with right:
            st.subheader("Explore the demo")
            st.write("Transfer to another demo account, pay a bill, repay a credit card, or make a simulated deposit.")
            st.info("Demo usernames: alice, bob, charlie\n\nPassword for each: DemoBank123!")
            st.caption("Three failed logins lock that account for 60 seconds. Demo OTPs are displayed in the app.")
        st.stop()

    username = st.session_state["user"]
    st.session_state["last_activity"] = now

    @st.fragment(run_every="5s")
    def watchdog():
        if time.time() - st.session_state.get("last_activity", 0) >= SESSION_SECONDS:
            sign_out("Your session expired after five minutes of inactivity. Please log in again.")
            st.rerun()
    watchdog()
    try:
        data = store.load()
    except BankError as error:
        st.error(str(error))
        st.stop()
    user = data["users"][username]
    history = user_history(data, username)
    pending = st.session_state.get("pending")
    if pending and (pending["closed"] or now >= pending["expires_at"]):
        st.session_state.pop("pending", None)
        pending = None
        st.warning("The previous OTP request is no longer active. Start a new transaction.")
    busy = pending is not None
    with st.sidebar:
        st.subheader(user["name"])
        st.caption(f"Demo account · {username}")
        page = st.radio("Banking services", ["Dashboard", "Payments & deposits", "Transaction history"], key="navigation")
        st.divider()
        st.write("OTP validity: 60 seconds")
        st.write("Session timeout: 5 minutes")
        if st.button("Log out", width="stretch"):
            sign_out("You have logged out. Any unconfirmed transaction was cancelled.")
            st.rerun()
    if "receipt" in st.session_state:
        receipt = st.session_state.pop("receipt")
        st.success(f"{receipt['kind']} completed: {money(receipt['amount_cents'])}. New balance: {money(receipt['balance_cents'])}.")
        st.caption(f"Receipt {receipt['id']} · {receipt['timestamp']}")
    st.subheader(f"Hello, {user['name'].split()[0]}")
    a, b, c = st.columns(3)
    a.metric("Available balance", money(user["balance_cents"]))
    b.metric("Completed activities", len(history))
    c.metric("Total outgoing", money(sum(int(Decimal(r["Amount (RM)"]) * 100) for r in history if r["Direction"] == "Debit")))

    def request(kind, amount, target):
        try:
            st.session_state["pending"] = store.prepare(username, kind, amount, target)
            st.rerun()
        except (BankError, OSError) as error:
            st.error(str(error))

    if page == "Dashboard":
        st.subheader("Your account at a glance")
        st.write("Choose Payments & deposits in the sidebar to begin. Every transaction requires an OTP before the balance changes.")
        values = [user["opening_cents"] / 100] + [float(row["Balance (RM)"]) for row in history]
        chart = pd.DataFrame({"Activity": range(len(values)), "Balance (RM)": values}).set_index("Activity")
        if history:
            st.line_chart(chart, color="#177c80")
        else:
            st.scatter_chart(chart, color="#177c80")
        if history:
            st.subheader("Spending by service")
            debits = pd.DataFrame([r for r in history if r["Direction"] == "Debit"])
            if not debits.empty:
                debits["Amount (RM)"] = debits["Amount (RM)"].astype(float)
                st.bar_chart(debits.groupby("Type")["Amount (RM)"].sum(), color="#177c80")
            st.subheader("Recent activity")
            st.dataframe(list(reversed(history[-5:])), hide_index=True, width="stretch")
        else:
            st.info("No transactions yet. Your first completed transaction will appear here.")
    elif page == "Payments & deposits" and not busy:
        st.subheader("Make a transaction")
        transfer, bill, card, deposit = st.tabs(["Transfer", "Bill payment", "Credit card", "Deposit"])
        with transfer:
            with st.form("transfer"):
                recipient = st.selectbox("Recipient", [key for key in data["users"] if key != username], disabled=busy, key="recipient")
                amount = st.text_input("Transfer amount (RM)", placeholder="100.00", disabled=busy, key="transfer_amount")
                if st.form_submit_button("Request transfer OTP", disabled=busy, type="primary"):
                    request("Transfer", amount, recipient)
        with bill:
            with st.form("bill"):
                service = st.selectbox("Service", BILL_SERVICES, disabled=busy, key="bill_service")
                reference = st.text_input("Bill reference (4-20 digits)", disabled=busy, key="bill_reference")
                amount = st.text_input("Bill amount (RM)", disabled=busy, key="bill_amount")
                if st.form_submit_button("Request bill payment OTP", disabled=busy, type="primary"):
                    request("Bill payment", amount, service + ":" + reference.strip())
        with card:
            with st.form("card"):
                number = st.text_input("Fictional credit card number (16 digits)", disabled=busy, key="card_number")
                amount = st.text_input("Credit card payment amount (RM)", disabled=busy, key="card_amount")
                if st.form_submit_button("Request credit card OTP", disabled=busy, type="primary"):
                    request("Credit card payment", amount, number)
        with deposit:
            st.caption("This simulates a cash deposit. No payment gateway is connected.")
            with st.form("deposit"):
                amount = st.text_input("Deposit amount (RM)", disabled=busy, key="deposit_amount")
                if st.form_submit_button("Request deposit OTP", disabled=busy, type="primary"):
                    request("Deposit", amount, "Simulated cash deposit")
    elif page == "Payments & deposits":
        st.subheader("Pending transaction")
        st.info("Confirm or cancel the transaction below before starting another.")
    else:
        st.subheader("Transaction history")
        selection = st.selectbox("Filter activities", ["All", "Credit", "Debit"])
        rows = [row for row in history if selection == "All" or row["Direction"] == selection]
        if rows:
            st.dataframe(list(reversed(rows)), hide_index=True, width="stretch")
        else:
            st.info("No transactions match this filter.")
        st.download_button("Download CSV", data=export_csv(rows), file_name=f"{username}_transactions.csv", mime="text/csv")

    if pending:
        st.divider()
        with st.container(border=True):
            st.subheader("Verify your transaction")
            target = "Card ending " + pending["target"][-4:] if pending["kind"] == "Credit card payment" else pending["target"]
            st.write(f"{pending['kind']} · {money(pending['cents'])} · {target}")
            st.info(f"Simulated OTP delivery: {pending['otp']}\n\nValid for 60 seconds from generation. No money has moved yet.")
            # Each request has its own widget keys, so old OTP input cannot carry over.
            with st.form("otp_" + pending["id"]):
                otp = st.text_input("Enter the 6-digit OTP", max_chars=6, key="code_" + pending["id"])
                confirmed = st.form_submit_button("Confirm transaction", type="primary")
            if confirmed:
                try:
                    st.session_state["receipt"] = store.confirm(username, pending, otp)
                    st.session_state.pop("pending", None)
                    st.rerun()
                except (BankError, OSError) as error:
                    st.error(str(error))
                    if pending["closed"]:
                        st.session_state.pop("pending", None)
            if st.button("Cancel transaction", key="cancel_" + pending["id"]):
                st.session_state.pop("pending", None)
                st.session_state["notice"] = "Transaction cancelled. Your balance was not changed."
                st.rerun()
    st.caption("Vela demo · Persistent JSON data · Salted PBKDF2 password hashes · UTC transaction timestamps")


if __name__ == "__main__":
    main()

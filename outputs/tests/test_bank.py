"""Behavior tests against disposable data; never modifies the demo bank file."""
import copy
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import traceback
import unittest
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "app.py"
spec = importlib.util.spec_from_file_location("bank", APP)
bank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bank)


class BankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.store = bank.BankStore(Path(self.temp.name) / "bank.json")

    def transact(self, kind, amount, target, username="alice", now=1000):
        pending = self.store.prepare(username, kind, amount, target, now=now)
        return self.store.confirm(username, pending, pending["otp"], now=now + 1)

    def test_login_hashes_and_lock_expiry(self):
        data = self.store.load()
        self.assertNotIn("DemoBank123!", json.dumps(data))
        self.assertNotEqual(data["users"]["alice"]["password_hash"], data["users"]["bob"]["password_hash"])
        self.assertEqual(self.store.authenticate(" ALICE ", "DemoBank123!", now=100), "alice")
        for _ in range(3):
            with self.assertRaises(bank.BankError):
                self.store.authenticate("alice", "wrong", now=100)
        with self.assertRaisesRegex(bank.BankError, "locked"):
            self.store.authenticate("alice", "DemoBank123!", now=159)
        reopened = bank.BankStore(self.store.path)
        self.assertEqual(reopened.authenticate("alice", "DemoBank123!", now=160), "alice")

    def test_invalid_amounts_and_details(self):
        for value in ["", "abc", "NaN", "Infinity", "-1", "0", "0.001", "1.234", "1000000.01"]:
            with self.subTest(value=value), self.assertRaises(bank.BankError):
                bank.amount_cents(value)
        self.assertEqual(bank.amount_cents("0.01"), 1)
        for kind, amount, target in [("Transfer", "6000", "bob"), ("Transfer", "1", "alice"),
                                     ("Transfer", "1", "missing"), ("Bill payment", "1", "Electricity:"),
                                     ("Bill payment", "1", "Unknown:123456"), ("Credit card payment", "1", "abc")]:
            with self.subTest(kind=kind, target=target), self.assertRaises(bank.BankError):
                self.store.prepare("alice", kind, amount, target)
        self.assertEqual(len(self.store.load()["transactions"]), 0)

    def test_wrong_otp_and_three_attempt_limit(self):
        pending = self.store.prepare("alice", "Transfer", "100", "bob", now=1000)
        before = self.store.load()
        for _ in range(3):
            wrong = "999999" if pending["otp"] != "999999" else "000000"
            with self.assertRaises(bank.BankError):
                self.store.confirm("alice", pending, wrong, now=1001)
        with self.assertRaises(bank.BankError):
            self.store.confirm("alice", pending, pending["otp"], now=1002)
        self.assertEqual(before, self.store.load())

    def test_retry_replaces_code_and_rejects_previous_codes(self):
        pending = self.store.prepare("alice", "Deposit", "1", "Simulated cash deposit", now=1000)
        first = pending["otp"]
        with self.assertRaisesRegex(bank.BankError, "new OTP"):
            self.store.confirm("alice", pending, "invalid", now=1059)
        second = pending["otp"]
        self.assertNotEqual(first, second)
        self.assertEqual(pending["expires_at"], 1119)
        with self.assertRaisesRegex(bank.BankError, "new OTP"):
            self.store.confirm("alice", pending, first, now=1060)
        self.assertNotIn(pending["otp"], (first, second))
        self.assertEqual(pending["attempts"], 2)
        self.assertEqual(len(self.store.load()["transactions"]), 0)
        self.store.confirm("alice", pending, pending["otp"], now=1061)
        self.assertEqual(len(self.store.load()["transactions"]), 1)

    def test_replacement_code_expires_at_60_seconds(self):
        pending = self.store.prepare("alice", "Deposit", "1", "Simulated cash deposit", now=1000)
        with self.assertRaises(bank.BankError):
            self.store.confirm("alice", pending, "invalid", now=1059)
        with self.assertRaisesRegex(bank.BankError, "expired"):
            self.store.confirm("alice", pending, pending["otp"], now=1119)
        self.assertTrue(pending["closed"])
        self.assertEqual(len(self.store.load()["transactions"]), 0)

    def test_code_generation_skips_already_issued_codes(self):
        with patch.object(bank.secrets, "randbelow", side_effect=[123, 123, 456]):
            pending = self.store.prepare("alice", "Deposit", "1", "Simulated cash deposit", now=1000)
            self.assertEqual(pending["otp"], "000123")
            with self.assertRaises(bank.BankError):
                self.store.confirm("alice", pending, "invalid", now=1001)
            self.assertEqual(pending["otp"], "000456")

    def test_expiry_at_exact_boundary(self):
        pending = self.store.prepare("alice", "Deposit", "100", "Simulated cash deposit", now=1000)
        with self.assertRaisesRegex(bank.BankError, "expired"):
            self.store.confirm("alice", pending, pending["otp"], now=1060)
        self.assertEqual(self.store.load()["users"]["alice"]["balance_cents"], 500000)

    def test_non_ascii_and_malformed_otps_are_rejected_without_crash(self):
        for entered in ("你好", "١٢٣٤٥٦", "１２３４５６", "", "abcdef", "12345", "1234567"):
            with self.subTest(entered=entered):
                pending = self.store.prepare("alice", "Deposit", "1", "Simulated cash deposit", now=1000)
                with self.assertRaisesRegex(bank.BankError, "Incorrect OTP"):
                    self.store.confirm("alice", pending, entered, now=1001)
                self.assertEqual(pending["attempts"], 1)
                self.assertEqual(len(self.store.load()["transactions"]), 0)

    def test_otp_expiring_while_waiting_for_lock_cannot_commit(self):
        pending = self.store.prepare("alice", "Deposit", "1", "Simulated cash deposit", now=1000)
        with patch.object(bank.time, "time", side_effect=[1059, 1061]):
            with self.assertRaisesRegex(bank.BankError, "expired"):
                self.store.confirm("alice", pending, pending["otp"])
        self.assertTrue(pending["closed"])
        self.assertEqual(self.store.load()["users"]["alice"]["balance_cents"], 500000)

    def test_transfer_balance_history_and_restart(self):
        pending = self.store.prepare("alice", "Transfer", "100.01", "bob", now=1000)
        self.assertEqual(self.store.load()["users"]["alice"]["balance_cents"], 500000)
        self.store.confirm("alice", pending, pending["otp"], now=1001)
        data = bank.BankStore(self.store.path).load()
        self.assertEqual(data["users"]["alice"]["balance_cents"], 489999)
        self.assertEqual(data["users"]["bob"]["balance_cents"], 260001)
        self.assertEqual(sum(u["balance_cents"] for u in data["users"].values()), 900000)
        self.assertEqual(bank.user_history(data, "alice")[0]["Direction"], "Debit")
        self.assertEqual(bank.user_history(data, "bob")[0]["Direction"], "Credit")
        self.assertEqual(bank.user_history(data, "bob")[0]["Balance (RM)"], "2600.01")

    def test_one_use_even_with_copied_request(self):
        pending = self.store.prepare("alice", "Deposit", "50", "Simulated cash deposit", now=1000)
        replay = copy.deepcopy(pending)
        self.store.confirm("alice", pending, pending["otp"], now=1001)
        with self.assertRaises(bank.BankError):
            self.store.confirm("alice", pending, pending["otp"], now=1002)
        with self.assertRaisesRegex(bank.BankError, "already"):
            self.store.confirm("alice", replay, replay["otp"], now=1002)
        self.assertEqual(self.store.load()["users"]["alice"]["balance_cents"], 505000)

    def test_wrong_user_cannot_confirm(self):
        pending = self.store.prepare("alice", "Transfer", "1", "bob", now=1000)
        with self.assertRaises(bank.BankError):
            self.store.confirm("bob", pending, pending["otp"], now=1001)
        self.assertEqual(len(self.store.load()["transactions"]), 0)

    def test_balance_rechecked_at_confirmation(self):
        pending = self.store.prepare("alice", "Transfer", "4000", "bob", now=1000)
        self.transact("Bill payment", "2000", "Water:123456")
        with self.assertRaisesRegex(bank.BankError, "Insufficient"):
            self.store.confirm("alice", pending, pending["otp"], now=1002)
        self.assertEqual(self.store.load()["users"]["bob"]["balance_cents"], 250000)

    def test_all_services_and_csv(self):
        self.transact("Bill payment", "12.50", "Electricity:123456")
        self.transact("Credit card payment", "20", "4111111111111111")
        self.transact("Deposit", "30", "Simulated cash deposit")
        data = self.store.load()
        self.assertEqual(data["users"]["alice"]["balance_cents"], 499750)
        self.assertNotIn("4111111111111111", json.dumps(data))
        rows = list(csv.DictReader(io.StringIO(bank.export_csv(bank.user_history(data, "alice")).decode("utf-8-sig"))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["Balance (RM)"], "4997.50")

    def test_concurrent_deposits_keep_all_updates(self):
        requests = [self.store.prepare("alice", "Deposit", "1", "Simulated cash deposit", now=1000) for _ in range(10)]
        errors = []
        def execute(pending):
            try:
                bank.BankStore(self.store.path).confirm("alice", pending, pending["otp"], now=1001)
            except Exception:
                errors.append(traceback.format_exc())
        threads = [threading.Thread(target=execute, args=(request,)) for request in requests]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.store.load()["users"]["alice"]["balance_cents"], 501000)
        self.assertEqual(len(self.store.load()["transactions"]), 10)

    def test_corrupt_data_preserved(self):
        self.store.path.write_text("broken JSON", encoding="utf-8")
        with self.assertRaises(bank.BankError):
            bank.BankStore(self.store.path)
        self.assertEqual(self.store.path.read_text(encoding="utf-8"), "broken JSON")

    def test_failed_write_does_not_commit(self):
        pending = self.store.prepare("alice", "Transfer", "1", "bob", now=1000)
        original = self.store.load()
        def failed_save(data):
            raise OSError("Simulated disk failure")
        self.store.save = failed_save
        with self.assertRaises(OSError):
            self.store.confirm("alice", pending, pending["otp"], now=1001)
        self.assertFalse(pending["closed"])
        self.assertEqual(self.store.load(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)

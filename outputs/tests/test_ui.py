import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import logging

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "work" / "python-packages"))
from streamlit.testing.v1 import AppTest
from streamlit import config
config.set_option("logger.level", "error")
for name in ("streamlit.runtime.scriptrunner.script_runner", "streamlit.runtime.media_file_manager", "streamlit.runtime.scriptrunner_utils.script_run_context"):
    logging.getLogger(name).setLevel(logging.ERROR)


class UITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        os.environ["VIRTUAL_BANK_DATA"] = str(Path(self.temp.name) / "bank.json")
        self.addCleanup(lambda: os.environ.pop("VIRTUAL_BANK_DATA", None))
        self.app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        self.assertEqual(len(self.app.exception), 0)

    def button(self, label):
        return next(b for b in self.app.button if b.label == label)

    def login(self):
        self.app.text_input(key="login_username").set_value("alice")
        self.app.text_input(key="login_password").set_value("DemoBank123!")
        self.button("Log in").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.metric[0].value, "RM 5,000.00")

    def payments(self):
        self.app.radio(key="navigation").set_value("Payments & deposits").run()

    def otp_input(self):
        pending = self.app.session_state["pending"]
        suffix = f"_{pending['attempts']}" if pending["attempts"] else ""
        return self.app.text_input(key="code_" + pending["id"] + suffix)

    def confirm(self):
        pending = self.app.session_state["pending"]
        countdown = next(metric for metric in self.app.metric if metric.label == "OTP expires in")
        self.assertGreater(int(countdown.value.split()[0]), 0)
        self.otp_input().set_value(pending["otp"])
        self.button("Confirm transaction").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertTrue(len(self.app.success) > 0)

    def test_login_errors_and_logout(self):
        self.app.text_input(key="login_username").set_value("alice")
        self.app.text_input(key="login_password").set_value("wrong")
        self.button("Log in").click().run()
        self.assertIn("Invalid", self.app.error[0].value)
        self.login()
        self.button("Log out").click().run()
        self.assertEqual(len(self.app.metric), 0)
        self.assertTrue(self.button("Log in"))

    def test_transfer_wrong_otp_then_success_and_recipient(self):
        self.login()
        self.payments()
        self.app.selectbox(key="recipient").set_value("bob")
        self.app.text_input(key="transfer_amount").set_value("100.01")
        self.button("Request transfer OTP").click().run()
        self.assertEqual(self.app.metric[0].value, "RM 5,000.00")
        pending = self.app.session_state["pending"]
        previous_code = pending["otp"]
        wrong = "000000" if pending["otp"] != "000000" else "999999"
        self.app.text_input(key="code_" + pending["id"]).set_value(wrong)
        self.button("Confirm transaction").click().run()
        self.assertIn("Incorrect OTP", self.app.error[0].value)
        self.assertEqual(self.app.metric[0].value, "RM 5,000.00")
        replacement = self.app.session_state["pending"]["otp"]
        self.assertNotEqual(previous_code, replacement)
        self.assertEqual(self.otp_input().value, "")
        self.assertTrue(any(replacement in message.value for message in self.app.info))
        self.otp_input().set_value(previous_code)
        self.button("Confirm transaction").click().run()
        self.assertIn("Incorrect OTP", self.app.error[0].value)
        self.assertEqual(self.app.metric[0].value, "RM 5,000.00")
        self.confirm()
        self.assertEqual(self.app.metric[0].value, "RM 4,899.99")
        self.app.radio(key="navigation").set_value("Transaction history").run()
        self.assertEqual(len(self.app.dataframe), 1)
        self.assertIn("Transfer", self.app.dataframe[0].value["Type"].tolist())
        self.button("Log out").click().run()
        self.app.text_input(key="login_username").set_value("bob")
        self.app.text_input(key="login_password").set_value("DemoBank123!")
        self.button("Log in").click().run()
        self.assertEqual(self.app.metric[0].value, "RM 2,600.01")
        self.assertEqual(len(self.app.exception), 0)

    def test_bill_card_deposit_and_charts(self):
        self.login()
        self.payments()
        self.app.text_input(key="bill_reference").set_value("123456")
        self.app.text_input(key="bill_amount").set_value("12.50")
        self.button("Request bill payment OTP").click().run()
        self.confirm()
        self.app.text_input(key="card_number").set_value("4111111111111111")
        self.app.text_input(key="card_amount").set_value("20")
        self.button("Request credit card OTP").click().run()
        self.confirm()
        self.app.text_input(key="deposit_amount").set_value("30")
        self.button("Request deposit OTP").click().run()
        self.confirm()
        self.assertEqual(self.app.metric[0].value, "RM 4,997.50")
        self.app.radio(key="navigation").set_value("Dashboard").run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertTrue(any(s.value == "Spending by service" for s in self.app.subheader))

    def test_validation_cancel_expiry_and_timeout(self):
        self.login()
        self.payments()
        self.app.text_input(key="transfer_amount").set_value("9999")
        self.button("Request transfer OTP").click().run()
        self.assertIn("Insufficient balance", self.app.error[0].value)
        self.app.text_input(key="transfer_amount").set_value("10")
        self.button("Request transfer OTP").click().run()
        self.button("Cancel transaction").click().run()
        self.assertEqual(self.app.metric[0].value, "RM 5,000.00")
        self.app.text_input(key="transfer_amount").set_value("10")
        self.button("Request transfer OTP").click().run()
        self.app.session_state["pending"]["expires_at"] = time.time() - 1
        self.app.run()
        self.assertTrue(any("no longer active" in w.value for w in self.app.warning))
        self.assertEqual(self.app.metric[0].value, "RM 5,000.00")
        self.app.session_state["last_activity"] = time.time() - 301
        self.app.run()
        self.assertEqual(len(self.app.metric), 0)
        self.assertTrue(any("session expired" in i.value for i in self.app.info))

    def test_unicode_otp_shows_error_instead_of_exception(self):
        self.login()
        self.payments()
        self.app.text_input(key="deposit_amount").set_value("1")
        self.button("Request deposit OTP").click().run()
        pending = self.app.session_state["pending"]
        self.app.text_input(key="code_" + pending["id"]).set_value("你好")
        self.button("Confirm transaction").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertIn("Incorrect OTP", self.app.error[0].value)
        self.assertEqual(self.app.metric[0].value, "RM 5,000.00")

    def test_countdown_decreases_resets_on_retry_and_disappears_on_expiry(self):
        self.login()
        self.payments()
        self.app.text_input(key="deposit_amount").set_value("1")
        self.button("Request deposit OTP").click().run()
        def seconds():
            return int(next(m.value for m in self.app.metric if m.label == "OTP expires in").split()[0])
        self.assertGreaterEqual(seconds(), 58)
        self.app.session_state["pending"]["expires_at"] = time.time() + 20
        self.app.run()
        self.assertGreaterEqual(seconds(), 18)
        self.assertLessEqual(seconds(), 20)
        self.otp_input().set_value("wrong")
        self.button("Confirm transaction").click().run()
        self.assertGreaterEqual(seconds(), 58)
        self.app.session_state["pending"]["expires_at"] = time.time() - 1
        self.app.run()
        self.assertFalse(any(m.label == "OTP expires in" for m in self.app.metric))
        self.assertFalse(any(b.label == "Confirm transaction" for b in self.app.button))
        self.assertTrue(any("no longer active" in w.value for w in self.app.warning))
        self.assertEqual(self.app.metric[0].value, "RM 5,000.00")

    def test_session_warning_and_stay_signed_in(self):
        self.login()
        self.app.session_state["last_activity"] = time.time() - 250
        self.app.run()
        self.assertTrue(any("about to expire" in warning.value for warning in self.app.warning))
        before = self.app.session_state["last_activity"]
        self.button("Stay signed in").click().run()
        self.assertGreater(self.app.session_state["last_activity"], before)
        self.assertFalse(any("about to expire" in warning.value for warning in self.app.warning))
        self.assertTrue(any("Auto logout in 05:00" in item.value for item in self.app.markdown))

    def test_background_reruns_and_otp_expiry_do_not_renew_session(self):
        self.login()
        self.payments()
        self.app.text_input(key="deposit_amount").set_value("1")
        self.button("Request deposit OTP").click().run()
        last_activity = time.time() - 100
        self.app.session_state["last_activity"] = last_activity
        self.app.session_state["pending"]["expires_at"] = time.time() - 1
        self.app.run()
        self.assertEqual(self.app.session_state["last_activity"], last_activity)
        self.app.run()
        self.assertEqual(self.app.session_state["last_activity"], last_activity)
        self.app.radio(key="navigation").set_value("Dashboard").run()
        self.assertGreater(self.app.session_state["last_activity"], last_activity)

    def test_demo_timeout_logs_out_and_clears_pending_transaction(self):
        self.login()
        self.app.selectbox(key="session_duration").set_value("30 seconds (demo)").run()
        self.assertEqual(self.app.session_state["timeout_seconds"], 30)
        self.payments()
        self.app.text_input(key="deposit_amount").set_value("1")
        self.button("Request deposit OTP").click().run()
        self.app.session_state["last_activity"] = time.time() - 31
        self.app.run()
        self.assertTrue(any("30 seconds" in notice.value and "automatically logged out" in notice.value for notice in self.app.info))
        self.assertEqual(len(self.app.metric), 0)
        with self.assertRaises(KeyError):
            self.app.session_state["pending"]
        with self.assertRaises(KeyError):
            self.app.session_state["user"]
        self.login()
        self.assertEqual(self.app.selectbox(key="session_duration").value, "5 minutes")

    def test_stay_signed_in_cannot_revive_expired_session(self):
        self.login()
        self.app.session_state["last_activity"] = time.time() - 301
        self.button("Stay signed in").click().run()
        self.assertTrue(self.button("Log in"))
        self.assertTrue(any("automatically logged out" in notice.value for notice in self.app.info))
        self.assertEqual(len(self.app.metric), 0)

    def test_longer_timeout_cannot_revive_expired_demo_session(self):
        self.login()
        self.app.selectbox(key="session_duration").set_value("30 seconds (demo)").run()
        self.app.session_state["last_activity"] = time.time() - 31
        self.app.selectbox(key="session_duration").set_value("5 minutes").run()
        self.assertTrue(self.button("Log in"))
        self.assertTrue(any("30 seconds" in notice.value and "automatically logged out" in notice.value for notice in self.app.info))
        self.assertEqual(len(self.app.metric), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

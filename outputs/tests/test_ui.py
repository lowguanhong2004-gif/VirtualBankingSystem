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

    def confirm(self):
        pending = self.app.session_state["pending"]
        self.app.text_input(key="code_" + pending["id"]).set_value(pending["otp"])
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
        wrong = "000000" if pending["otp"] != "000000" else "999999"
        self.app.text_input(key="code_" + pending["id"]).set_value(wrong)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

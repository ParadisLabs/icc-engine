import unittest
from urllib.parse import urlparse, parse_qs

from icc_v2.execution.ctrader import (
    CTraderConfigurationError,
    CTraderDemoAdapter,
    CTraderDemoConfig,
    CTraderExecutionDisabled,
)


def config(**overrides):
    values = dict(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://example.invalid/callback",
        access_token="test-access",
        account_id=123456,
        environment="demo",
    )
    values.update(overrides)
    return CTraderDemoConfig(**values)


class CTraderAdapterTests(unittest.TestCase):
    def test_demo_config_accepted(self):
        self.assertEqual(CTraderDemoAdapter(config()).environment, "demo")

    def test_live_environment_rejected(self):
        with self.assertRaises(CTraderConfigurationError):
            config(environment="live")

    def test_missing_secret_rejected(self):
        with self.assertRaises(CTraderConfigurationError):
            config(client_secret="")

    def test_invalid_account_id_rejected(self):
        with self.assertRaises(CTraderConfigurationError):
            config(account_id=0)

    def test_authorization_url_defaults_to_read_only_scope(self):
        parsed = urlparse(CTraderDemoAdapter.authorization_url(
            "abc", "https://example.invalid/callback"
        ))
        query = parse_qs(parsed.query)
        self.assertEqual(query["scope"], ["accounts"])
        self.assertEqual(query["client_id"], ["abc"])

    def test_invalid_scope_rejected(self):
        with self.assertRaises(CTraderConfigurationError):
            CTraderDemoAdapter.authorization_url("abc", "https://example.invalid", scope="admin")

    def test_order_submission_is_fail_closed(self):
        with self.assertRaises(CTraderExecutionDisabled):
            CTraderDemoAdapter(config()).submit_order({"side": "BUY"})

    def test_order_modification_is_fail_closed(self):
        with self.assertRaises(CTraderExecutionDisabled):
            CTraderDemoAdapter(config()).amend_order(1)

    def test_position_actions_are_fail_closed(self):
        with self.assertRaises(CTraderExecutionDisabled):
            CTraderDemoAdapter(config()).close_position(1)


if __name__ == "__main__":
    unittest.main()

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
    def test_environment_loader_requires_all_credentials(self):
        from icc_v2.execution.ctrader import CTraderConfigurationError
        with self.assertRaises(CTraderConfigurationError):
            CTraderDemoConfig.from_env({})

    def test_environment_loader_defaults_to_demo(self):
        values = {
            "CTRADER_CLIENT_ID": "id",
            "CTRADER_CLIENT_SECRET": "secret",
            "CTRADER_REDIRECT_URI": "https://example.invalid/callback",
            "CTRADER_ACCESS_TOKEN": "token",
            "CTRADER_ACCOUNT_ID": "123456",
        }
        loaded = CTraderDemoConfig.from_env(values)
        self.assertEqual(loaded.environment, "demo")
        self.assertEqual(loaded.account_id, 123456)

    def test_environment_loader_rejects_live_environment(self):
        values = {
            "CTRADER_CLIENT_ID": "id",
            "CTRADER_CLIENT_SECRET": "secret",
            "CTRADER_REDIRECT_URI": "https://example.invalid/callback",
            "CTRADER_ACCESS_TOKEN": "token",
            "CTRADER_ACCOUNT_ID": "123456",
            "CTRADER_ENVIRONMENT": "live",
        }
        with self.assertRaises(CTraderConfigurationError):
            CTraderDemoConfig.from_env(values)

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

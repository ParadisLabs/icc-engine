import unittest

from icc_v2.data.fx_universe import (
    event_relevant_instruments, parse_instrument, validate_fx_universe,
)


class FxUniverseTests(unittest.TestCase):
    def test_event_currency_selects_pairs_without_direction(self):
        self.assertEqual(
            event_relevant_instruments("gbp", ["EUR_USD", "GBP_USD", "GBP_JPY", "USD_JPY"]),
            ("GBP_USD", "GBP_JPY"),
        )

    def test_pair_orientation_is_preserved_and_duplicates_removed(self):
        self.assertEqual(
            validate_fx_universe(["eur_usd", "EUR_USD", "USD_JPY"]),
            ("EUR_USD", "USD_JPY"),
        )
        self.assertEqual(parse_instrument("usd_jpy").base_currency, "USD")

    def test_invalid_currency_and_pair_rejected(self):
        with self.assertRaises(ValueError):
            event_relevant_instruments("US")
        with self.assertRaises(ValueError):
            parse_instrument("EURUSD")
        with self.assertRaises(ValueError):
            validate_fx_universe([])


if __name__ == "__main__":
    unittest.main()

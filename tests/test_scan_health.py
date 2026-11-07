import unittest

from engine.scan_health import analysed_counts


class ScanHealthTests(unittest.TestCase):
    def test_zero_of_six_is_detected(self):
        self.assertEqual(analysed_counts("[icc] analysed 0/6 symbols"), (0, 6))

    def test_partial_scan_is_reported(self):
        self.assertEqual(analysed_counts("[icc] analysed 4/6 symbols"), (4, 6))

    def test_missing_summary_is_not_healthy(self):
        self.assertIsNone(analysed_counts("scan completed without summary"))


if __name__ == "__main__":
    unittest.main()

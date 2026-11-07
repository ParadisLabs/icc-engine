"""Fail-closed validation for the ICC scheduled market-data scan."""
import re
import sys
from pathlib import Path


SUMMARY = re.compile(r"\\[icc\\] analysed (\\d+)/(\\d+) symbols")


def analysed_counts(text):
    match = SUMMARY.search(text)
    if not match:
        return None
    return tuple(map(int, match.groups()))


def main(path):
    log = Path(path)
    if not log.is_file():
        print("ICC health gate: scan log is missing")
        return 1
    counts = analysed_counts(log.read_text(errors="replace"))
    if counts is None:
        print("ICC health gate: analysed-symbol summary is missing")
        return 1
    analysed, total = counts
    print(f"ICC health gate: analysed {analysed}/{total} symbols")
    if total < 1 or analysed < 1:
        print("ICC health gate: FAIL — no symbols received usable market data")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "main_scan.log"))

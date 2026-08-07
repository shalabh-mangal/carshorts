"""Crawl real car specs into JSON sheets — now a thin alias for trusted-source research.

  python -m carshorts.sourcing.crawl "Tata Nexon" "Maruti Suzuki Fronx"

Historically this read Wikipedia's infobox directly. Wikipedia has been REMOVED
as a fact source — it repeatedly shipped wrong India-market specs (the "1.5L
Fronx" / wrong-Brezza class) that presented as verified fact. `crawl` now
delegates to `webresearch.research`, which grounds facts in tier-1 sources only
(CarDekho / CarWale / Autocar / official maker sites) with corroboration-based
confidence, and flags anything unverified as [CLAIMED] for the owner's CarDekho
check. Kept as a command so existing scripts/skills keep working.

Price is never crawled here (--no-price by default); it stays the owner's one-off
CarDekho/official lookup (CLAUDE.md).
"""
from __future__ import annotations

import argparse

from carshorts.sourcing.webresearch import research


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl car specs into JSON sheets (trusted-source research; "
                    "Wikipedia removed).")
    parser.add_argument("cars", nargs="+", help="Car names, e.g. \"Tata Nexon\".")
    parser.add_argument("--price", action="store_true",
                        help="Also attempt a web price (owner still verifies). Off by default.")
    args = parser.parse_args()

    print("note: `crawl` now uses trusted-source research (Wikipedia removed).")
    written = 0
    for car in args.cars:
        sheet = research(car, want_price=args.price)
        if sheet.specs:
            written += 1
    print(f"\nDone. {written}/{len(args.cars)} sheet(s) with grounded specs.")


if __name__ == "__main__":
    main()

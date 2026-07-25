"""Crawl real car specs into JSON files the harness can replay.

  python -m carshorts.sourcing.crawl "Tata Nexon" "Mahindra Thar" "Maruti Suzuki Fronx"
  python -m carshorts.sourcing.crawl --out specs --min-specs 2 "Hyundai Creta"

Each car becomes specs/<slug>.json — a serialized SpecSheet. A car that yields
fewer than --min-specs source-bound facts is skipped and reported, not written
(an empty sheet would give the harness nothing to test).

This is deliberately a SEPARATE step from the harness: crawl once (network,
slow), then measure many times offline against the saved sheets. It keeps the
expensive/rate-limited model runs decoupled from fetching.
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from carshorts.adapters.specsource import WikipediaSpecSource


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl car specs into JSON sheets.")
    parser.add_argument("cars", nargs="+", help="Car names, e.g. \"Tata Nexon\".")
    parser.add_argument("--out", default="specs", help="Output dir (default: specs).")
    parser.add_argument("--min-specs", type=int, default=2,
                        help="Skip cars yielding fewer than this many source-bound specs.")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds between requests (polite to Wikipedia; default 1.5).")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    source = WikipediaSpecSource()

    written, skipped = 0, 0
    for idx, car in enumerate(args.cars):
        if idx > 0 and args.delay > 0:
            time.sleep(args.delay)
        try:
            sheet = source.fetch(car)
        except LookupError as exc:
            print(f"[skip] {car}: {exc}")
            skipped += 1
            continue
        except Exception as exc:  # noqa: BLE001 — network/parse failure: report, keep going
            print(f"[error] {car}: {exc}")
            skipped += 1
            continue

        if len(sheet.specs) < args.min_specs:
            print(f"[skip] {car}: only {len(sheet.specs)} spec(s) found "
                  f"(need {args.min_specs}).")
            skipped += 1
            continue

        path = out_dir / f"{_slug(car)}.json"
        path.write_text(sheet.model_dump_json(indent=2))
        names = ", ".join(s.name for s in sheet.specs)
        print(f"[ok]   {car}: {len(sheet.specs)} specs [{names}] -> {path}")
        written += 1

    print(f"\nDone. {written} sheet(s) written to {out_dir}/, {skipped} skipped.")


if __name__ == "__main__":
    main()

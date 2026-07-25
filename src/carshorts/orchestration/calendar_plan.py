"""Experiment scheduler — deliberate A/B across the content calendar.

  python -m carshorts.orchestration.calendar_plan --build      # (re)generate the next 8 slots
  python -m carshorts.orchestration.calendar_plan              # show the calendar

Each slot pre-assigns the experiment variables — car, persona, format, hook
type, length bucket, music mood — rotated so cohorts stay comparable. The
analyst can then attribute performance to CHOICES instead of coincidence.
`pipeline --next` consumes the top pending slot.
"""
from __future__ import annotations

import argparse
import datetime
import itertools
import json
from pathlib import Path

CALENDAR = Path("data/calendar.json")

CARS = ["Hyundai Creta", "Maruti Suzuki Brezza", "Tata Punch", "Kia Sonet",
        "Mahindra Scorpio", "Toyota Fortuner", "Maruti Suzuki Fronx", "Tata Tiago"]
PERSONAS = ["deadpan", "hype"]
FORMATS = ["spotlight", "five_things", "vs", "mythbust"]
LENGTHS = ["45s", "55s"]


def build(slots: int = 8) -> None:
    persona_cycle = itertools.cycle(PERSONAS)
    format_cycle = itertools.cycle(FORMATS)
    length_cycle = itertools.cycle(LENGTHS)
    entries = []
    for i in range(slots):
        entries.append({
            "slot": i + 1,
            "car": CARS[i % len(CARS)],
            "persona": next(persona_cycle),
            "format": next(format_cycle),
            "length_bucket": next(length_cycle),
            "status": "pending",
            "note": "pre-assigned A/B — keep unless a news event overrides",
        })
    CALENDAR.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR.write_text(json.dumps(
        {"built": datetime.date.today().isoformat(), "entries": entries},
        indent=2, ensure_ascii=False))
    print(f"calendar built: {slots} slots -> {CALENDAR}")
    show()


def show() -> None:
    if not CALENDAR.exists():
        print("no calendar — build one: python -m carshorts.orchestration.calendar_plan --build")
        return
    data = json.loads(CALENDAR.read_text())
    for entry in data["entries"]:
        print(f"  {entry['slot']:2}. {entry['car']:24} {entry['persona']:8} "
              f"{entry['format']:12} {entry['length_bucket']:4} {entry['status']}")


def next_pending() -> dict | None:
    if not CALENDAR.exists():
        return None
    data = json.loads(CALENDAR.read_text())
    for entry in data["entries"]:
        if entry["status"] == "pending":
            return entry
    return None


def mark(slot: int, status: str) -> None:
    data = json.loads(CALENDAR.read_text())
    for entry in data["entries"]:
        if entry["slot"] == slot:
            entry["status"] = status
    CALENDAR.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--slots", type=int, default=8)
    args = ap.parse_args()
    if args.build:
        build(args.slots)
    else:
        show()


if __name__ == "__main__":
    main()

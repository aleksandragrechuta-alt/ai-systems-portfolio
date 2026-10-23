"""Builds a run history with the real totals of the live system and prints the reviews.

The live system's results from 1 September to 22 October 2026 (from its own run log,
published in projects/01-support-triage-automation.md) are recreated here as
placeholder tickets, so the review code produces the same numbers. Ticket ids and
reasons are placeholders (the real tickets are client data and stay private), so the
demo prints only the outcome tables.

Run: python3 demo.py
"""

import os
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone

from review import review, to_markdown
from run import SCHEMA

REAL_RESULTS = {
    # month start: (answered in full, first reply then a person, straight to a person, filtered)
    date(2026, 9, 1): (395, 367, 30, 180),
    date(2026, 10, 1): (162, 297, 43, 158),
}
LABELS = ("approved reply (placeholder)", "first reply, then a person (placeholder)",
          "sent straight to a person (placeholder)", "filtered (placeholder)")
ACTIONS = ("send", "first_reply", "hold", "filter")


def build_history(path: str) -> None:
    rows, n = [], 0
    for month, counts in REAL_RESULTS.items():
        for action, label, count in zip(ACTIONS, LABELS, counts):
            for i in range(count):
                n += 1
                at = datetime(month.year, month.month, 1, tzinfo=timezone.utc) + timedelta(hours=i % (20 * 24))
                rows.append(("demo", f"T{n}", action, label, 0, at.isoformat()))
    with sqlite3.connect(path) as db:
        db.execute(SCHEMA)
        db.executemany("INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)", rows)


if __name__ == "__main__":
    path = os.path.join(tempfile.mkdtemp(), "runs.sqlite")
    build_history(path)
    sept, octo, end = date(2026, 9, 1), date(2026, 10, 1), date(2026, 10, 23)
    print(to_markdown(review(path, sept, end), summary_only=True))
    print(to_markdown(review(path, octo, end, previous=(sept, octo)), summary_only=True))

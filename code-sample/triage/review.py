"""Weekly review: how the triage performed, and what a person should look at first.

Reads the run history that run.py writes (live runs only, dry runs are left out)
and builds a report with:

- how many tickets were answered automatically and how many went to a person,
  compared with the week before;
- "needs attention first": AI failures and AI choices the rules had to block;
- why tickets were held, and which approved replies were used;
- knowledge gaps: questions the knowledge base could not answer;
- a random sample of automatically answered tickets for the weekly quality audit.
"""

from __future__ import annotations

import random
import sqlite3
from collections import Counter
from datetime import date, timedelta

# Reasons a person should check before anything else, most urgent first.
ATTENTION_FIRST = [
    ("AI step failed", "the AI call failed"),
    ("unknown reply id", "the AI chose a reply that does not exist"),
    ("knowledge-base check failed: unknown source", "the AI cited a source that does not exist"),
    ("knowledge-base check failed: answer contains a forbidden phrase", "the answer promised money or mentioned automation"),
]

# Held tickets that point to a missing or weak knowledge-base entry.
KNOWLEDGE_GAP_REASONS = ("AI unsure", "knowledge-base check failed: answer has no knowledge-base source")


def _week(db: sqlite3.Connection, start: date) -> list[tuple[str, str, str]]:
    end = start + timedelta(days=7)
    return db.execute(
        "SELECT ticket_id, action, reason FROM decisions "
        "WHERE dry_run = 0 AND decided_at >= ? AND decided_at < ? ORDER BY decided_at",
        (start.isoformat(), end.isoformat()),
    ).fetchall()


def _rate(rows) -> float:
    return sum(1 for _, action, _ in rows if action == "send") / len(rows) if rows else 0.0


def weekly_review(db_path: str, week_start: date, audit_size: int = 10) -> dict:
    with sqlite3.connect(db_path) as db:
        rows = _week(db, week_start)
        previous = _week(db, week_start - timedelta(days=7))

    sent = [(t, r) for t, action, r in rows if action == "send"]
    held = [(t, r) for t, action, r in rows if action == "hold"]

    attention = []
    for prefix, meaning in ATTENTION_FIRST:
        tickets = [t for t, r in held if r.startswith(prefix)]
        if tickets:
            attention.append({"issue": meaning, "tickets": tickets})

    # Same week, same sample: the audit list can be reproduced later.
    sampler = random.Random(week_start.isoformat())
    audit = sampler.sample([t for t, _ in sent], min(audit_size, len(sent)))

    return {
        "week_start": week_start.isoformat(),
        "tickets": len(rows),
        "answered_automatically": len(sent),
        "held_for_a_person": len(held),
        "automation_rate": _rate(rows),
        "automation_rate_last_week": _rate(previous),
        "needs_attention_first": attention,
        "held_by_reason": Counter(r for _, r in held).most_common(),
        "approved_replies_used": Counter(r.removeprefix("approved reply ") for _, r in sent if r.startswith("approved reply")).most_common(),
        "knowledge_gaps": [t for t, r in held if r in KNOWLEDGE_GAP_REASONS],
        "quality_audit_sample": sorted(audit),
    }


def to_markdown(review: dict) -> str:
    change = (review["automation_rate"] - review["automation_rate_last_week"]) * 100
    lines = [
        f"# Weekly review, week of {review['week_start']}",
        "",
        f"- Tickets: {review['tickets']}",
        f"- Answered automatically: {review['answered_automatically']} ({review['automation_rate']:.0%}, {change:+.0f} points on last week)",
        f"- Held for a person: {review['held_for_a_person']}",
        "",
        "## Needs attention first",
    ]
    if review["needs_attention_first"]:
        lines += [f"- {a['issue']}: {', '.join(a['tickets'])}" for a in review["needs_attention_first"]]
    else:
        lines.append("- Nothing this week.")
    lines += ["", "## Why tickets were held"]
    lines += [f"- {reason}: {count}" for reason, count in review["held_by_reason"]] or ["- None."]
    lines += ["", "## Approved replies used"]
    lines += [f"- {reply}: {count}" for reply, count in review["approved_replies_used"]] or ["- None."]
    lines += ["", "## Knowledge gaps (questions to add to the knowledge base)"]
    lines.append(f"- Tickets: {', '.join(review['knowledge_gaps'])}" if review["knowledge_gaps"] else "- None.")
    lines += ["", "## Quality audit: re-read these automatic answers"]
    lines.append(f"- Tickets: {', '.join(review['quality_audit_sample'])}" if review["quality_audit_sample"] else "- None.")
    return "\n".join(lines) + "\n"

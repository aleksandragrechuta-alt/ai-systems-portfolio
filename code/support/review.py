"""Performance review: how the support automation did, and what a person should look at first.

Reads the run history that run.py writes (live runs only, dry runs are left out)
for any period, usually a week or a month, and compares it with the period before.

The report has:

- the four outcomes: answered in full, immediate first reply then a person,
  straight to a person, and filtered out (junk, duplicates, business mail);
- "needs attention first": AI failures and AI choices the rules had to block;
- why tickets went to a person, and which approved replies did the work;
- knowledge gaps: questions the knowledge base could not answer;
- a random sample of automatic answers for the weekly quality audit.
"""

from __future__ import annotations

import random
import sqlite3
from collections import Counter
from datetime import date, timedelta

OUTCOMES = [
    ("send", "Answered in full"),
    ("first_reply", "Immediate first reply, then a person"),
    ("hold", "Sent straight to a person"),
    ("filter", "Junk, duplicates and business mail filtered out"),
]

# Reasons a person should check before anything else, most urgent first.
ATTENTION_FIRST = [
    ("AI step failed", "the AI call failed"),
    ("unknown reply id", "the AI chose a reply that does not exist"),
    ("knowledge-base check failed: unknown source", "the AI cited a source that does not exist"),
    ("knowledge-base check failed: answer contains a forbidden phrase", "the answer promised money or mentioned automation"),
]

# Held tickets that point to a missing or weak knowledge-base entry.
KNOWLEDGE_GAP_REASONS = ("AI unsure", "knowledge-base check failed: answer has no knowledge-base source")


def _period(db: sqlite3.Connection, start: date, end: date) -> list[tuple[str, str, str]]:
    return db.execute(
        "SELECT ticket_id, action, reason FROM decisions "
        "WHERE dry_run = 0 AND decided_at >= ? AND decided_at < ? ORDER BY decided_at",
        (start.isoformat(), end.isoformat()),
    ).fetchall()


def _counts(rows) -> dict:
    c = Counter(action for _, action, _ in rows)
    return {action: c[action] for action, _ in OUTCOMES}


def review(db_path: str, start: date, end: date, previous: tuple[date, date] | None = None,
           audit_size: int = 10) -> dict:
    """Review the decisions from start (included) to end (not included)."""
    with sqlite3.connect(db_path) as db:
        rows = _period(db, start, end)
        before = _period(db, *previous) if previous else []

    sent = [(t, r) for t, action, r in rows if action == "send"]
    for_person = [(t, r) for t, action, r in rows if action in ("hold", "first_reply")]

    attention = []
    for prefix, meaning in ATTENTION_FIRST:
        tickets = [t for t, r in for_person if r.startswith(prefix)]
        if tickets:
            attention.append({"issue": meaning, "tickets": tickets})

    # Same period, same sample: the audit list can be reproduced later.
    sampler = random.Random(start.isoformat())
    audit = sampler.sample([t for t, _ in sent], min(audit_size, len(sent)))

    return {
        "start": start.isoformat(),
        "end": (end - timedelta(days=1)).isoformat(),
        "tickets": len(rows),
        "outcomes": _counts(rows),
        "previous": {"tickets": len(before), "outcomes": _counts(before)} if previous else None,
        "needs_attention_first": attention,
        "for_a_person_by_reason": Counter(r for _, r in for_person).most_common(),
        "approved_replies_used": Counter(r.removeprefix("approved reply ") for _, r in sent
                                         if r.startswith("approved reply")).most_common(),
        "knowledge_gaps": [t for t, r in for_person if r in KNOWLEDGE_GAP_REASONS],
        "quality_audit_sample": sorted(audit, key=lambda t: (len(t), t)),
    }


def weekly_review(db_path: str, week_start: date, audit_size: int = 10) -> dict:
    week_end = week_start + timedelta(days=7)
    return review(db_path, week_start, week_end, (week_start - timedelta(days=7), week_start), audit_size)


def _share(n: int, total: int) -> str:
    return f"{n / total:.0%}" if total else "0%"


def to_markdown(r: dict, summary_only: bool = False) -> str:
    total = r["tickets"]
    o = r["outcomes"]
    lines = [f"# Review, {r['start']} to {r['end']}", ""]

    header = "| Outcome | Tickets | Share |"
    if r["previous"]:
        header += " Period before |"
    lines += [header, "|---|---|---|" + ("---|" if r["previous"] else "")]
    for action, label in OUTCOMES:
        row = f"| {label} | {o[action]} | {_share(o[action], total)} |"
        if r["previous"]:
            p = r["previous"]
            row += f" {p['outcomes'][action]} ({_share(p['outcomes'][action], p['tickets'])}) |"
        lines.append(row)
    lines.append(f"| **All tickets** | **{total}** | |" + (f" **{r['previous']['tickets']}** |" if r["previous"] else ""))

    at_once = o["send"] + o["first_reply"]
    lines += ["", f"**Answered or given a first reply at once: {at_once} ({_share(at_once, total)}).**"]
    if summary_only:
        return "\n".join(lines) + "\n"
    lines += ["", "## Needs attention first"]
    lines += [f"- {a['issue']}: {', '.join(a['tickets'])}" for a in r["needs_attention_first"]] or ["- Nothing in this period."]
    lines += ["", "## Why tickets went to a person"]
    lines += [f"- {reason}: {count}" for reason, count in r["for_a_person_by_reason"]] or ["- None."]
    lines += ["", "## Approved replies used"]
    lines += [f"- {reply}: {count}" for reply, count in r["approved_replies_used"]] or ["- None."]
    lines += ["", "## Knowledge gaps (questions to add to the knowledge base)"]
    lines.append(f"- Tickets: {', '.join(r['knowledge_gaps'])}" if r["knowledge_gaps"] else "- None.")
    lines += ["", "## Quality audit: re-read these automatic answers"]
    lines.append(f"- Tickets: {', '.join(r['quality_audit_sample'])}" if r["quality_audit_sample"] else "- None.")
    return "\n".join(lines) + "\n"

"""One triage run: read open tickets, route each one, act, and log the result.

A dry run (the default) decides everything but changes nothing in the
helpdesk, so the decisions can be reviewed before a live run.
Every decision is saved to a SQLite run history, which the weekly review reads.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from helpdesk_api import HelpdeskClient
from routing import Classifier, Decision, Ticket, route, run_report

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    run_id TEXT, ticket_id TEXT, action TEXT, reason TEXT, dry_run INTEGER, decided_at TEXT
)
"""


def duplicate_key(ticket: Ticket) -> str:
    """Same customer, same subject (ignoring Re:/Fwd: and case) = the same question asked twice."""
    subject = re.sub(r"^\s*((re|fwd?)\s*:\s*)+", "", ticket.subject, flags=re.IGNORECASE).strip().lower()
    return f"{ticket.requester.lower()}|{subject}"


def act(client: HelpdeskClient, decision: Decision) -> None:
    if decision.action == "send":
        client.reply(decision.ticket_id, decision.reply)
    elif decision.action == "first_reply":
        client.reply(decision.ticket_id, decision.reply)
        client.hold_for_person(decision.ticket_id, decision.reason)
    elif decision.action == "filter":
        client.set_aside(decision.ticket_id, decision.reason)
    else:
        client.hold_for_person(decision.ticket_id, decision.reason)


def run(client: HelpdeskClient, classify: Classifier, db_path: str, dry_run: bool = True) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    decisions, first_seen = [], {}
    with sqlite3.connect(db_path) as db:
        db.execute(SCHEMA)
        for raw in client.open_tickets():
            ticket = Ticket(str(raw["id"]), raw.get("subject", ""), raw.get("description", ""),
                            raw.get("requester", ""))
            key = duplicate_key(ticket)
            decision = route(ticket, classify, duplicate_of=first_seen.get(key) if ticket.requester else None)
            first_seen.setdefault(key, ticket.id)
            if not dry_run:
                act(client, decision)
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, ticket.id, decision.action, decision.reason, int(dry_run),
                 datetime.now(timezone.utc).isoformat()),
            )
            decisions.append(decision)
    return {"run_id": run_id, "dry_run": dry_run, **run_report(decisions)}

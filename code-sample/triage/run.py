"""One triage run: read open tickets, route each one, act, and log the result.

A dry run (the default) decides everything but changes nothing in the
helpdesk, so the decisions can be reviewed before a live run.
Every decision is saved to a SQLite run history.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from helpdesk_api import HelpdeskClient
from routing import Classifier, Ticket, route, run_report

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    run_id TEXT, ticket_id TEXT, action TEXT, reason TEXT, dry_run INTEGER, decided_at TEXT
)
"""


def run(client: HelpdeskClient, classify: Classifier, db_path: str, dry_run: bool = True) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    decisions = []
    with sqlite3.connect(db_path) as db:
        db.execute(SCHEMA)
        for raw in client.open_tickets():
            ticket = Ticket(str(raw["id"]), raw.get("subject", ""), raw.get("description", ""))
            decision = route(ticket, classify)
            if not dry_run:
                if decision.action == "send":
                    client.reply(ticket.id, decision.reply)
                else:
                    client.hold_for_person(ticket.id, decision.reason)
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, ticket.id, decision.action, decision.reason, int(dry_run),
                 datetime.now(timezone.utc).isoformat()),
            )
            decisions.append(decision)
    return {"run_id": run_id, "dry_run": dry_run, **run_report(decisions)}

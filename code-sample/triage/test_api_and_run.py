"""Tests for the helpdesk client and a full run. No network: the HTTP layer is a fake."""

import json
import os
import sqlite3
import tempfile
import unittest

from helpdesk_api import HelpdeskClient, HelpdeskError
from routing import AIChoice
from run import run


class FakeHelpdesk:
    """Answers requests from a queue of prepared responses and records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, method, url, headers, body):
        self.requests.append((method, url, json.loads(body) if body else None))
        status, payload, *extra = self.responses.pop(0)
        return status, (extra[0] if extra else {}), json.dumps(payload).encode()


def client(fake, waits=None):
    return HelpdeskClient("https://shop.example-helpdesk.com", "test-token", transport=fake,
                          sleep=(waits.append if waits is not None else lambda s: None))


class Client(unittest.TestCase):
    def test_reads_every_page_of_open_tickets(self):
        fake = FakeHelpdesk([
            (200, {"tickets": [{"id": 1}], "next_page": "https://shop.example-helpdesk.com/api/v2/tickets?page=2"}),
            (200, {"tickets": [{"id": 2}], "next_page": None}),
        ])
        self.assertEqual([t["id"] for t in client(fake).open_tickets()], [1, 2])

    def test_rate_limit_waits_as_long_as_the_server_asks(self):
        waits = []
        fake = FakeHelpdesk([(429, {}, {"Retry-After": "7"}), (200, {"tickets": []})])
        client(fake, waits).open_tickets()
        self.assertEqual(waits, [7.0])
        self.assertEqual(len(fake.requests), 2)

    def test_wrong_credentials_stop_at_once(self):
        fake = FakeHelpdesk([(401, {})])
        with self.assertRaises(HelpdeskError):
            client(fake).open_tickets()
        self.assertEqual(len(fake.requests), 1)

    def test_gives_up_after_the_retry_limit(self):
        fake = FakeHelpdesk([(503, {})] * 4)
        with self.assertRaises(HelpdeskError):
            client(fake).open_tickets()
        self.assertEqual(len(fake.requests), 4)

    def test_held_ticket_gets_an_internal_note_not_a_public_reply(self):
        fake = FakeHelpdesk([(200, {})])
        client(fake).hold_for_person("9", "protected: refund")
        comment = fake.requests[0][2]["ticket"]["comment"]
        self.assertFalse(comment["public"])
        self.assertIn("protected: refund", comment["body"])


OPEN_TICKETS = (200, {"tickets": [
    {"id": 1, "subject": "Where is my order?", "description": "I ordered on Monday."},
    {"id": 2, "subject": "Refund", "description": "I want my money back."},
], "next_page": None})


def ai(ticket):
    return AIChoice("approved_reply", reply_id="order_tracking")


class FullRun(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "runs.sqlite")

    def test_dry_run_changes_nothing_in_the_helpdesk(self):
        fake = FakeHelpdesk([OPEN_TICKETS])
        report = run(client(fake), ai, self.db, dry_run=True)
        self.assertEqual([r[0] for r in fake.requests], ["GET"])
        self.assertEqual((report["sent"], report["held_for_a_person"]), (1, 1))

    def test_live_run_replies_and_holds(self):
        fake = FakeHelpdesk([OPEN_TICKETS, (200, {}), (200, {})])
        run(client(fake), ai, self.db, dry_run=False)
        reply, hold = fake.requests[1][2], fake.requests[2][2]
        self.assertTrue(reply["ticket"]["comment"]["public"])
        self.assertIn("needs-person", hold["ticket"]["additional_tags"])

    def test_every_decision_is_saved_to_the_run_history(self):
        run(client(FakeHelpdesk([OPEN_TICKETS])), ai, self.db)
        with sqlite3.connect(self.db) as db:
            rows = db.execute("SELECT ticket_id, action, reason FROM decisions ORDER BY ticket_id").fetchall()
        self.assertEqual(rows, [("1", "send", "approved reply order_tracking"), ("2", "hold", "protected: refund")])


if __name__ == "__main__":
    unittest.main()

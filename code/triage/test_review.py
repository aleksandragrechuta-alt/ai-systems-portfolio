"""Tests for the performance review."""

import os
import sqlite3
import tempfile
import unittest
from datetime import date

import demo
from review import review, to_markdown, weekly_review
from run import SCHEMA

WEEK = date(2026, 10, 12)


def history(rows):
    """rows: (ticket_id, action, reason, dry_run, decided_at)"""
    path = os.path.join(tempfile.mkdtemp(), "runs.sqlite")
    with sqlite3.connect(path) as db:
        db.execute(SCHEMA)
        db.executemany("INSERT INTO decisions VALUES ('run', ?, ?, ?, ?, ?)", rows)
    return path


THIS_WEEK = [
    ("1", "send", "approved reply order_tracking", 0, "2026-10-12T09:00:00+00:00"),
    ("2", "send", "approved reply order_tracking", 0, "2026-10-13T09:00:00+00:00"),
    ("3", "send", "knowledge-base answer from kb-003", 0, "2026-10-14T09:00:00+00:00"),
    ("4", "hold", "protected: refund", 0, "2026-10-14T10:00:00+00:00"),
    ("5", "hold", "AI unsure", 0, "2026-10-15T09:00:00+00:00"),
    ("6", "hold", "AI step failed: TimeoutError", 0, "2026-10-16T09:00:00+00:00"),
    ("7", "first_reply", "first reply ask_order_number, then a person", 0, "2026-10-16T09:30:00+00:00"),
    ("8", "filter", "filtered: newsletter", 0, "2026-10-17T09:00:00+00:00"),
    ("9", "send", "approved reply size_exchange", 1, "2026-10-16T10:00:00+00:00"),  # dry run
]
LAST_WEEK = [
    ("10", "send", "approved reply order_tracking", 0, "2026-10-06T09:00:00+00:00"),
    ("11", "hold", "protected: refund", 0, "2026-10-07T09:00:00+00:00"),
]


class WeeklyReview(unittest.TestCase):
    def setUp(self):
        self.review = weekly_review(history(THIS_WEEK + LAST_WEEK), WEEK, audit_size=2)

    def test_counts_the_four_outcomes_of_live_decisions_only(self):
        self.assertEqual(self.review["tickets"], 8)
        self.assertEqual(self.review["outcomes"], {"send": 3, "first_reply": 1, "hold": 3, "filter": 1})

    def test_compares_with_the_week_before(self):
        self.assertEqual(self.review["previous"], {"tickets": 2, "outcomes": {"send": 1, "first_reply": 0, "hold": 1, "filter": 0}})

    def test_ai_failures_come_first(self):
        self.assertEqual(self.review["needs_attention_first"], [{"issue": "the AI call failed", "tickets": ["6"]}])

    def test_lists_knowledge_gaps(self):
        self.assertEqual(self.review["knowledge_gaps"], ["5"])

    def test_counts_approved_replies(self):
        self.assertEqual(self.review["approved_replies_used"], [("order_tracking", 2)])

    def test_audit_sample_is_drawn_from_automatic_answers_and_repeatable(self):
        sample = self.review["quality_audit_sample"]
        self.assertEqual(len(sample), 2)
        self.assertTrue(set(sample) <= {"1", "2", "3"})
        self.assertEqual(sample, weekly_review(history(THIS_WEEK), WEEK, audit_size=2)["quality_audit_sample"])

    def test_markdown_report(self):
        text = to_markdown(self.review)
        self.assertIn("| Answered in full | 3 | 38% | 1 (50%) |", text)
        self.assertIn("- the AI call failed: 6", text)


class RealTotals(unittest.TestCase):
    """The demo history must reproduce the live system's published results exactly."""

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "runs.sqlite")
        demo.build_history(self.path)

    def test_september_to_22_october(self):
        r = review(self.path, date(2026, 9, 1), date(2026, 10, 23))
        self.assertEqual(r["tickets"], 1632)
        self.assertEqual(r["outcomes"], {"send": 557, "first_reply": 664, "hold": 73, "filter": 338})
        self.assertIn("Answered or given a first reply at once: 1221 (75%)", to_markdown(r, summary_only=True))

    def test_october_compared_with_september(self):
        r = review(self.path, date(2026, 10, 1), date(2026, 10, 23), previous=(date(2026, 9, 1), date(2026, 10, 1)))
        self.assertEqual((r["tickets"], r["previous"]["tickets"]), (660, 972))


if __name__ == "__main__":
    unittest.main()

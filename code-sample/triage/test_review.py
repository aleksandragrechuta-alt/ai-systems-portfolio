"""Tests for the weekly review."""

import os
import sqlite3
import tempfile
import unittest
from datetime import date

from review import to_markdown, weekly_review
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
    ("7", "send", "approved reply size_exchange", 1, "2026-10-16T10:00:00+00:00"),  # dry run
]
LAST_WEEK = [
    ("8", "send", "approved reply order_tracking", 0, "2026-10-06T09:00:00+00:00"),
    ("9", "hold", "protected: refund", 0, "2026-10-07T09:00:00+00:00"),
]


class WeeklyReview(unittest.TestCase):
    def setUp(self):
        self.review = weekly_review(history(THIS_WEEK + LAST_WEEK), WEEK, audit_size=2)

    def test_counts_only_live_decisions_of_that_week(self):
        self.assertEqual((self.review["tickets"], self.review["answered_automatically"]), (6, 3))

    def test_compares_with_last_week(self):
        self.assertEqual(self.review["automation_rate"], 0.5)
        self.assertEqual(self.review["automation_rate_last_week"], 0.5)

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
        self.assertIn("Answered automatically: 3 (50%, +0 points on last week)", text)
        self.assertIn("- the AI call failed: 6", text)


if __name__ == "__main__":
    unittest.main()

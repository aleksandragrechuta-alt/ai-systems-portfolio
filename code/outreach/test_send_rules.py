"""Tests for the outreach send rules. Run with: python3 -m unittest -v"""

import unittest
from datetime import datetime, timezone
from email.message import EmailMessage

from send_rules import (BANNED_WORDS, auto_reply_kind, bounce_reason, check_text_rules, company_key,
                        in_send_window, is_bounce, parse_send_window, send_address, send_decision)

VOICE = {"Send window": "Mon-Fri 09:00-12:00"}
TUESDAY_9_UTC = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)   # 11:00 in Barcelona, 10:00 in Lisbon
TUESDAY_14_UTC = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)  # 16:00 in Barcelona
SATURDAY_9_UTC = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)


def row(**fields):
    base = {"_row": 2, "Status": "APPROVED", "Company": "Casa Nova", "Country": "Spain", "City": "Barcelona",
            "Email": "hello@casanova.example.com", "Website": "https://casanova.example.com", "Analysis Notes": "",
            "Email Subject": "Wall lamps for Casa Nova", "Email Body": "Hello"}
    return {**base, **fields}


def message(**headers):
    msg = EmailMessage()
    for name, value in headers.items():
        msg[name.replace("_", "-")] = value
    return msg


class WritingRules(unittest.TestCase):
    def test_banned_words_and_dashes_are_caught(self):
        problems = check_text_rules("Our stunning lamps — handmade in Barcelona", BANNED_WORDS)
        self.assertEqual(problems, ["contains an em or en dash", "banned word: handmade", "banned word: stunning"])

    def test_curly_apostrophes_do_not_hide_a_banned_phrase(self):
        self.assertEqual(check_text_rules("Don’t miss out", BANNED_WORDS), ["banned word: don't miss out"])

    def test_clean_text_passes(self):
        self.assertEqual(check_text_rules("A wireless wall lamp for your reading corner.", BANNED_WORDS), [])


class SendWindow(unittest.TestCase):
    def test_reads_the_window_setting(self):
        self.assertEqual(parse_send_window("Mon-Fri 09:00-12:00"), ({0, 1, 2, 3, 4}, 9.0, 12.0))

    def test_morning_in_barcelona_sends(self):
        self.assertTrue(in_send_window(row(), VOICE, TUESDAY_9_UTC)[0])

    def test_afternoon_waits(self):
        ok, desc = in_send_window(row(), VOICE, TUESDAY_14_UTC)
        self.assertFalse(ok)
        self.assertEqual(desc, "Mon-Fri 09:00-12:00 their time (Europe/Madrid)")

    def test_weekend_waits(self):
        self.assertFalse(in_send_window(row(), VOICE, SATURDAY_9_UTC)[0])

    def test_canary_islands_use_their_own_time_zone(self):
        ok, desc = in_send_window(row(City="Las Palmas"), VOICE, TUESDAY_14_UTC)
        self.assertIn("Atlantic/Canary", desc)

    def test_window_no_run_can_reach_does_not_hold_forever(self):
        self.assertTrue(in_send_window(row(Country="Japan"), VOICE, TUESDAY_14_UTC)[0])


class WhoMayBeEmailed(unittest.TestCase):
    def test_only_an_address_at_the_start_of_the_cell_is_used(self):
        self.assertEqual(send_address(row(Email="shop@x.example.com (alt: info@x.example.com)")), "shop@x.example.com")
        self.assertEqual(send_address(row(Email="Not found (form only; listings suggest info@x.example.com)")), "")

    def test_company_is_recognised_by_its_domain(self):
        self.assertEqual(company_key(row(Website="https://www.casanova.example.com/shop")), "casanova.example.com")
        self.assertEqual(company_key(row(Website="", Email="casanova@gmail.com")), "")


class InboxReading(unittest.TestCase):
    def test_bounce_is_recognised(self):
        self.assertTrue(is_bounce(message(From="Mail Delivery System <mailer-daemon@x.example.com>", Subject="Undelivered")))

    def test_hard_and_soft_bounces(self):
        self.assertEqual(bounce_reason("Status: 5.1.1\nDiagnostic-Code: smtp; 550 user unknown"), (True, "550 user unknown"))
        self.assertFalse(bounce_reason("Status: 4.2.2\nDiagnostic-Code: smtp; mailbox full")[0])

    def test_out_of_office_is_not_a_real_reply(self):
        self.assertEqual(auto_reply_kind(message(From="ana@shop.example.com", Subject="Out of office"), ""), "auto")

    def test_anti_spam_challenge_is_recognised(self):
        msg = message(From="noreply@mailinblack.com", Subject="Please confirm you are human")
        self.assertEqual(auto_reply_kind(msg, ""), "challenge")

    def test_a_real_reply_is_a_real_reply(self):
        msg = message(From="ana@shop.example.com", Subject="Re: Wall lamps for your shop")
        self.assertEqual(auto_reply_kind(msg, "Thanks, could you send prices?"), "")


class OrderOfChecks(unittest.TestCase):
    def decide(self, r, sent_today=0, index=None, now=TUESDAY_9_UTC):
        return send_decision(r, VOICE, sent_today, 20, index or {}, now=now)

    def test_nothing_goes_without_a_persons_approval(self):
        self.assertEqual(self.decide(row(Status="Draft Ready"))[0], "skip")

    def test_daily_limit_waits_until_tomorrow(self):
        self.assertEqual(self.decide(row(), sent_today=20)[0], "wait")

    def test_unverified_address_is_held(self):
        self.assertEqual(self.decide(row(Email="Not found"))[0], "hold")

    def test_same_company_from_another_list_is_held(self):
        index = {"casanova.example.com": [{"tab": "Press", "row": 7, "company": "Casa Nova", "status": "Sent", "date": "2026-10-01"}]}
        self.assertEqual(self.decide(row(), index=index)[0], "hold")
        self.assertEqual(self.decide(row(**{"Analysis Notes": "send anyway"}), index=index)[0], "send")

    def test_outside_the_window_waits(self):
        self.assertEqual(self.decide(row(), now=TUESDAY_14_UTC)[0], "wait")

    def test_approved_in_the_window_sends(self):
        self.assertEqual(self.decide(row()), ("send", ""))


if __name__ == "__main__":
    unittest.main()

"""Tests for the routing rules. Run with: python -m unittest discover code-sample/triage"""

import unittest

from routing import AIChoice, Decision, Ticket, is_solved, route, run_report


def ai_returns(choice):
    return lambda ticket: choice


def ai_must_not_run(ticket):
    raise AssertionError("the AI must not see protected tickets")


class SafetyGates(unittest.TestCase):
    def test_refund_goes_to_a_person_before_the_ai(self):
        ticket = Ticket("t1", "Refund please", "I want my money back for the course.")
        decision = route(ticket, ai_must_not_run)
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "protected: refund")

    def test_unrecognised_charge_is_protected(self):
        ticket = Ticket("t2", "Charge", "I didn't authorize this payment on my card.")
        self.assertEqual(route(ticket, ai_must_not_run).reason, "protected: unrecognised charge")

    def test_lifetime_membership_is_protected(self):
        ticket = Ticket("t3", "Question", "I have a lifetime plan, can I add my partner?")
        self.assertEqual(route(ticket, ai_must_not_run).reason, "protected: lifetime membership")

    def test_very_frustrated_customer_is_protected(self):
        ticket = Ticket("t4", "Login", "THIS IS THE THIRD TIME I WRITE AND NOBODY ANSWERS")
        self.assertEqual(route(ticket, ai_must_not_run).reason, "protected: very frustrated customer")


class ApprovedReplies(unittest.TestCase):
    def test_approved_reply_is_sent_unchanged(self):
        ticket = Ticket("t5", "Password", "I forgot my password.")
        decision = route(ticket, ai_returns(AIChoice("approved_reply", reply_id="reset_password")))
        self.assertEqual(decision.action, "send")
        self.assertIn("reset your password", decision.reply)

    def test_reply_id_the_ai_made_up_is_held(self):
        ticket = Ticket("t6", "Password", "I forgot my password.")
        decision = route(ticket, ai_returns(AIChoice("approved_reply", reply_id="free_month")))
        self.assertEqual(decision.action, "hold")


class KnowledgeBaseAnswers(unittest.TestCase):
    ticket = Ticket("t7", "Subtitles", "Are there Spanish subtitles?")

    def test_answer_with_a_real_source_is_sent(self):
        choice = AIChoice("kb_answer", answer="Yes, every lesson has Spanish subtitles.", sources=["kb-003"])
        self.assertEqual(route(self.ticket, ai_returns(choice)).action, "send")

    def test_answer_without_source_is_held(self):
        choice = AIChoice("kb_answer", answer="Yes, every lesson has Spanish subtitles.")
        self.assertIn("no knowledge-base source", route(self.ticket, ai_returns(choice)).reason)

    def test_answer_with_invented_source_is_held(self):
        choice = AIChoice("kb_answer", answer="Yes.", sources=["kb-999"])
        self.assertIn("unknown source", route(self.ticket, ai_returns(choice)).reason)

    def test_answer_promising_money_is_held(self):
        choice = AIChoice("kb_answer", answer="Sorry! Here is a discount code.", sources=["kb-003"])
        self.assertEqual(route(self.ticket, ai_returns(choice)).action, "hold")

    def test_answer_revealing_the_automation_is_held(self):
        choice = AIChoice("kb_answer", answer="As an AI, I can confirm subtitles exist.", sources=["kb-003"])
        self.assertEqual(route(self.ticket, ai_returns(choice)).action, "hold")


class Failures(unittest.TestCase):
    def test_ai_outage_holds_the_ticket(self):
        def broken(ticket):
            raise TimeoutError

        decision = route(Ticket("t8", "App", "Does the app work offline?"), broken)
        self.assertEqual((decision.action, decision.reason), ("hold", "AI step failed: TimeoutError"))

    def test_unsure_ai_holds_the_ticket(self):
        decision = route(Ticket("t9", "Other", "Can you help me?"), ai_returns(AIChoice("unsure")))
        self.assertEqual(decision.action, "hold")


class Closing(unittest.TestCase):
    def test_only_a_real_customer_signal_closes(self):
        self.assertTrue(is_solved("Thank you!"))
        self.assertTrue(is_solved("it works now"))
        self.assertFalse(is_solved("Thanks, but it still doesn't work"))
        self.assertFalse(is_solved(""))


class Report(unittest.TestCase):
    def test_report_lists_every_held_ticket_with_its_reason(self):
        report = run_report([
            Decision("a", "send", "approved reply reset_password"),
            Decision("b", "hold", "protected: refund"),
        ])
        self.assertEqual((report["sent"], report["held_for_a_person"]), (1, 1))
        self.assertEqual(report["held"], [{"ticket": "b", "reason": "protected: refund"}])


if __name__ == "__main__":
    unittest.main()

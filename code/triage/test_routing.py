"""Tests for the routing rules. Run with: cd code/triage && python3 -m unittest -v"""

import unittest

from routing import AIChoice, Decision, Ticket, is_solved, route, run_report


def ai_returns(choice):
    return lambda ticket: choice


def ai_must_not_run(ticket):
    raise AssertionError("the AI must not see protected tickets")


class SafetyGates(unittest.TestCase):
    def test_refund_goes_to_a_person_before_the_ai(self):
        ticket = Ticket("t1", "Refund please", "I want my money back for these boots.")
        decision = route(ticket, ai_must_not_run)
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.reason, "protected: refund")

    def test_unrecognised_charge_is_protected(self):
        ticket = Ticket("t2", "Charge", "I didn't authorize this payment on my card.")
        self.assertEqual(route(ticket, ai_must_not_run).reason, "protected: unrecognised charge")

    def test_damaged_item_is_protected(self):
        ticket = Ticket("t3", "Order 1042", "The left shoe arrived damaged, the sole is coming off.")
        self.assertEqual(route(ticket, ai_must_not_run).reason, "protected: damaged or wrong item")

    def test_very_frustrated_customer_is_protected(self):
        ticket = Ticket("t4", "Order", "THIS IS THE THIRD TIME I WRITE AND NOBODY ANSWERS")
        self.assertEqual(route(ticket, ai_must_not_run).reason, "protected: very frustrated customer")


class ApprovedReplies(unittest.TestCase):
    def test_approved_reply_is_sent_unchanged(self):
        ticket = Ticket("t5", "Where is my order?", "I ordered on Monday, where is it?")
        decision = route(ticket, ai_returns(AIChoice("approved_reply", reply_id="order_tracking")))
        self.assertEqual(decision.action, "send")
        self.assertIn("tracking link", decision.reply)

    def test_reply_id_the_ai_made_up_is_held(self):
        ticket = Ticket("t6", "Where is my order?", "I ordered on Monday, where is it?")
        decision = route(ticket, ai_returns(AIChoice("approved_reply", reply_id="free_shipping_code")))
        self.assertEqual(decision.action, "hold")


class KnowledgeBaseAnswers(unittest.TestCase):
    ticket = Ticket("t7", "Sizes", "I am between a 38 and a 39, which should I take?")

    def test_answer_with_a_real_source_is_sent(self):
        choice = AIChoice("kb_answer", answer="Our shoes fit true to size, so between two sizes we recommend the 39.", sources=["kb-003"])
        self.assertEqual(route(self.ticket, ai_returns(choice)).action, "send")

    def test_answer_without_source_is_held(self):
        choice = AIChoice("kb_answer", answer="Our shoes fit true to size, so we recommend the 39.")
        self.assertIn("no knowledge-base source", route(self.ticket, ai_returns(choice)).reason)

    def test_answer_with_invented_source_is_held(self):
        choice = AIChoice("kb_answer", answer="Take the 39.", sources=["kb-999"])
        self.assertIn("unknown source", route(self.ticket, ai_returns(choice)).reason)

    def test_answer_promising_money_is_held(self):
        choice = AIChoice("kb_answer", answer="Sorry! Here is a discount code.", sources=["kb-003"])
        self.assertEqual(route(self.ticket, ai_returns(choice)).action, "hold")

    def test_answer_revealing_the_automation_is_held(self):
        choice = AIChoice("kb_answer", answer="As an AI, I recommend the 39.", sources=["kb-003"])
        self.assertEqual(route(self.ticket, ai_returns(choice)).action, "hold")


class Filtering(unittest.TestCase):
    def test_auto_reply_is_set_aside_without_the_ai(self):
        ticket = Ticket("t10", "Automatic reply: out of office", "I am away until Monday.")
        self.assertEqual(route(ticket, ai_must_not_run).action, "filter")

    def test_sales_pitch_is_set_aside(self):
        ticket = Ticket("t11", "Partnership opportunity", "We offer SEO services for shops like yours.")
        self.assertEqual(route(ticket, ai_must_not_run).reason, "filtered: sales pitch")

    def test_duplicate_is_set_aside(self):
        ticket = Ticket("t12", "Where is my order?", "Still waiting.")
        decision = route(ticket, ai_must_not_run, duplicate_of="t5")
        self.assertEqual((decision.action, decision.reason), ("filter", "filtered: duplicate of t5"))


class FirstReplies(unittest.TestCase):
    def test_first_reply_is_sent_and_a_person_finishes(self):
        ticket = Ticket("t13", "Exchange", "I want to change the colour of my order.")
        decision = route(ticket, ai_returns(AIChoice("first_reply", reply_id="ask_order_number")))
        self.assertEqual(decision.action, "first_reply")
        self.assertIn("order number", decision.reply)

    def test_first_reply_the_ai_made_up_is_held(self):
        ticket = Ticket("t14", "Exchange", "I want to change the colour of my order.")
        decision = route(ticket, ai_returns(AIChoice("first_reply", reply_id="free_gift")))
        self.assertEqual(decision.action, "hold")


class Failures(unittest.TestCase):
    def test_ai_outage_holds_the_ticket(self):
        def broken(ticket):
            raise TimeoutError

        decision = route(Ticket("t8", "Care", "How do I clean suede?"), broken)
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
    def test_report_counts_outcomes_and_lists_tickets_for_a_person(self):
        report = run_report([
            Decision("a", "send", "approved reply order_tracking"),
            Decision("b", "hold", "protected: refund"),
            Decision("c", "first_reply", "first reply ask_order_number, then a person"),
            Decision("d", "filter", "filtered: newsletter"),
        ])
        self.assertEqual((report["sent"], report["first_reply_then_person"], report["held_for_a_person"],
                          report["filtered"]), (1, 1, 1, 1))
        self.assertEqual([x["ticket"] for x in report["for_a_person"]], ["b", "c"])


if __name__ == "__main__":
    unittest.main()

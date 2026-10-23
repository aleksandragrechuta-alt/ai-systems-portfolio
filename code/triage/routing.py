"""Routing rules for AI-assisted support triage (simplified sample, online-shop example).

A ticket goes through four steps:

1. Filter (rules, no AI): auto-replies, newsletters, sales pitches and
   duplicates are set aside and never answered.
2. Safety gates (rules, no AI): protected cases go straight to a person,
   before the AI ever sees them.
3. One AI classification pass: the AI may only choose an approved reply,
   propose a knowledge-base answer, choose an approved first reply for a
   case a person has to finish, or say it is unsure.
4. Checks on the AI's choice (rules, no AI): anything that does not pass
   is held for a person instead of being sent.

Every ticket ends in one of four outcomes:
"send" (answered in full), "first_reply" (an immediate first reply, then a
person), "hold" (straight to a person) or "filter" (set aside).

The AI is passed in as a function, so the rules can be tested without it.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

# Replies a person has written and approved. The AI can pick one, never edit it.
APPROVED_REPLIES = {
    "order_tracking": "You can follow your order in My Account > Orders. The tracking link appears there as soon as the parcel leaves the warehouse.",
    "size_exchange": "You can request a size exchange in My Account > Returns within 30 days of delivery. The new size ships once we receive the original pair.",
    "return_policy": "Unused items can be returned within 30 days of delivery from My Account > Returns. You will receive a prepaid label by email.",
}

# Approved first replies: sent at once when a person has to finish the case,
# so the customer is not left waiting and the person gets what they need.
FIRST_REPLIES = {
    "ask_order_number": "Thanks for your message. Could you reply with your order number? Then we can check it straight away.",
    "passed_to_team": "Thanks for your message. We have passed it to our team, who will reply personally within one business day.",
}

# Curated knowledge base: the only source a knowledge-base answer may use.
KNOWLEDGE_BASE = {
    "kb-001": "In-stock items ship within 1 to 2 business days. Delivery in the EU takes 1 to 3 business days.",
    "kb-002": "Leather shoes can be cleaned with a soft dry cloth. Avoid water and direct heat.",
    "kb-003": "Our shoes fit true to size. Between two sizes, choose the larger one.",
}

# Protected topics: always a person, whatever the AI would say.
PROTECTED_PATTERNS = {
    "refund": r"\brefund|money back|reembolso",
    "billing dispute": r"\bchargeback|dispute|charged twice|double charged",
    "unrecognised charge": r"didn'?t (make|authori[sz]e)|unrecogni[sz]ed charge|don'?t recogni[sz]e",
    "damaged or wrong item": r"\b(damaged|broken|defective|wrong item|wrong size sent)\b",
    "legal or privacy": r"\blawyer|legal action|gdpr|delete my data",
}

# Mail that is not a customer question: never answered, never counted as work.
JUNK_PATTERNS = {
    "auto-reply": r"out of (the )?office|automatic reply|auto.?reply|delivery status notification",
    "newsletter": r"\bunsubscribe\b|view (this email )?in (your )?browser",
    "sales pitch": r"\bSEO services\b|guest post|partnership opportunity|increase your (traffic|sales)",
}

# A knowledge-base answer must never promise money or reveal the automation.
FORBIDDEN_IN_ANSWERS = r"\brefund|compensat|discount|\bAI\b|\bbot\b|automat|language model"

# Only these customer messages count as "solved"; anything else keeps the ticket open.
SOLVED_SIGNALS = r"^\s*(thanks?( you)?|thank you so much|solved|it works( now)?|all good|perfect|gracias)[\s!.]*$"

MAX_ANSWER_LENGTH = 600


@dataclass
class Ticket:
    id: str
    subject: str
    body: str
    requester: str = ""


@dataclass
class AIChoice:
    """What the AI classification pass returns."""
    kind: str                      # "approved_reply", "kb_answer", "first_reply" or "unsure"
    reply_id: str | None = None    # for approved_reply and first_reply
    answer: str | None = None      # for kb_answer
    sources: list[str] = field(default_factory=list)  # kb ids the answer is based on


@dataclass
class Decision:
    ticket_id: str
    action: str                    # "send", "first_reply", "hold" or "filter"
    reason: str
    reply: str | None = None


Classifier = Callable[[Ticket], AIChoice]


def junk_reason(ticket: Ticket) -> str | None:
    """Return why a message is not a customer question, or None. Rules only, no AI."""
    text = f"{ticket.subject}\n{ticket.body}"
    for reason, pattern in JUNK_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return reason
    return None


def protected_reason(ticket: Ticket) -> str | None:
    """Return why a ticket is protected, or None. Rules only, no AI."""
    text = f"{ticket.subject}\n{ticket.body}"
    for reason, pattern in PROTECTED_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return reason
    if is_very_frustrated(text):
        return "very frustrated customer"
    return None


def is_very_frustrated(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    shouting = len(letters) >= 20 and sum(c.isupper() for c in letters) / len(letters) > 0.6
    angry_words = re.search(r"\b(scam|unacceptable|worst|furious|ridiculous)\b", text, re.IGNORECASE)
    return bool(shouting or angry_words or text.count("!") >= 4)


def check_kb_answer(choice: AIChoice) -> str | None:
    """Return why a knowledge-base answer may not be sent, or None if it passes."""
    if not choice.answer or not choice.answer.strip():
        return "empty answer"
    if not choice.sources:
        return "answer has no knowledge-base source"
    unknown = [s for s in choice.sources if s not in KNOWLEDGE_BASE]
    if unknown:
        return f"unknown source {', '.join(unknown)}"
    if re.search(FORBIDDEN_IN_ANSWERS, choice.answer, re.IGNORECASE):
        return "answer contains a forbidden phrase"
    if len(choice.answer) > MAX_ANSWER_LENGTH:
        return "answer too long"
    return None


def route(ticket: Ticket, classify: Classifier, duplicate_of: str | None = None) -> Decision:
    """Decide what happens to one ticket."""
    if duplicate_of:
        return Decision(ticket.id, "filter", f"filtered: duplicate of {duplicate_of}")
    junk = junk_reason(ticket)
    if junk:
        return Decision(ticket.id, "filter", f"filtered: {junk}")

    reason = protected_reason(ticket)
    if reason:
        return Decision(ticket.id, "hold", f"protected: {reason}")

    try:
        choice = classify(ticket)
    except Exception as error:  # outage, timeout, bad response: never guess
        return Decision(ticket.id, "hold", f"AI step failed: {type(error).__name__}")

    if choice.kind == "approved_reply":
        if choice.reply_id not in APPROVED_REPLIES:
            return Decision(ticket.id, "hold", f"unknown reply id {choice.reply_id!r}")
        return Decision(ticket.id, "send", f"approved reply {choice.reply_id}", APPROVED_REPLIES[choice.reply_id])

    if choice.kind == "kb_answer":
        problem = check_kb_answer(choice)
        if problem:
            return Decision(ticket.id, "hold", f"knowledge-base check failed: {problem}")
        return Decision(ticket.id, "send", f"knowledge-base answer from {', '.join(choice.sources)}", choice.answer)

    if choice.kind == "first_reply":
        if choice.reply_id not in FIRST_REPLIES:
            return Decision(ticket.id, "hold", f"unknown reply id {choice.reply_id!r}")
        return Decision(ticket.id, "first_reply", f"first reply {choice.reply_id}, then a person", FIRST_REPLIES[choice.reply_id])

    return Decision(ticket.id, "hold", "AI unsure")


def is_solved(customer_message: str) -> bool:
    """Close a ticket only on a real customer signal."""
    return re.match(SOLVED_SIGNALS, customer_message, re.IGNORECASE) is not None


def run_report(decisions: list[Decision]) -> dict:
    """Counts for the run report, plus every ticket a person has to look at, with its reason."""
    actions = Counter(d.action for d in decisions)
    return {
        "tickets": len(decisions),
        "sent": actions["send"],
        "first_reply_then_person": actions["first_reply"],
        "held_for_a_person": actions["hold"],
        "filtered": actions["filter"],
        "for_a_person": [{"ticket": d.ticket_id, "reason": d.reason}
                         for d in decisions if d.action in ("hold", "first_reply")],
    }

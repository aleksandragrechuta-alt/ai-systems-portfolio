"""Routing rules for AI-assisted support triage (simplified sample).

A ticket goes through three steps:

1. Safety gates (rules, no AI): protected cases go straight to a person,
   before the AI ever sees them.
2. One AI classification pass: the AI may only choose an approved reply,
   propose a knowledge-base answer, or say it is unsure.
3. Checks on the AI's choice (rules, no AI): anything that does not pass
   is held for a person instead of being sent.

The AI is passed in as a function, so the rules can be tested without it.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

# Replies a person has written and approved. The AI can pick one, never edit it.
APPROVED_REPLIES = {
    "reset_password": "You can reset your password here: {reset_link}. The link is valid for 24 hours.",
    "certificate_download": "Your certificate is in My Account > Certificates. You can download it as a PDF there.",
    "course_access": "Your course is in My Account > My Courses. If it is not there, reply with the email you used to buy it.",
}

# Curated knowledge base: the only source a knowledge-base answer may use.
KNOWLEDGE_BASE = {
    "kb-001": "Courses stay available for as long as your membership is active.",
    "kb-002": "Video lessons can be watched on desktop and in the mobile app.",
    "kb-003": "Subtitles are available in English and Spanish for every lesson.",
}

# Protected topics: always a person, whatever the AI would say.
PROTECTED_PATTERNS = {
    "refund": r"\brefund|money back|reembolso",
    "billing dispute": r"\bchargeback|dispute|charged twice|double charged",
    "unrecognised charge": r"didn'?t (make|authori[sz]e)|unrecogni[sz]ed charge|don'?t recogni[sz]e",
    "lifetime membership": r"\blifetime\b",
    "legal or privacy": r"\blawyer|legal action|gdpr|delete my data",
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


@dataclass
class AIChoice:
    """What the AI classification pass returns."""
    kind: str                      # "approved_reply", "kb_answer" or "unsure"
    reply_id: str | None = None    # for approved_reply
    answer: str | None = None      # for kb_answer
    sources: list[str] = field(default_factory=list)  # kb ids the answer is based on


@dataclass
class Decision:
    ticket_id: str
    action: str                    # "send" or "hold"
    reason: str
    reply: str | None = None


Classifier = Callable[[Ticket], AIChoice]


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


def route(ticket: Ticket, classify: Classifier) -> Decision:
    """Decide what happens to one ticket."""
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

    return Decision(ticket.id, "hold", "AI unsure")


def is_solved(customer_message: str) -> bool:
    """Close a ticket only on a real customer signal."""
    return re.match(SOLVED_SIGNALS, customer_message, re.IGNORECASE) is not None


def run_report(decisions: list[Decision]) -> dict:
    """Counts for the run report, plus every held ticket with its reason."""
    actions = Counter(d.action for d in decisions)
    return {
        "tickets": len(decisions),
        "sent": actions["send"],
        "held_for_a_person": actions["hold"],
        "held": [{"ticket": d.ticket_id, "reason": d.reason} for d in decisions if d.action == "hold"],
    }

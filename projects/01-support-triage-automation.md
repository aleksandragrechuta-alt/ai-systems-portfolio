# Support triage automation

**Context:** independent client work for a large online academy platform. **Status:** live since August 2026. Runs are started by hand after a dry run, never on a schedule.

## The problem

One support lead (me) runs the customer support queue in Zendesk. Customers were waiting more than 7 days for an answer. Most tickets were repeat questions with a known correct answer, but every ticket still needed a person to read it.

## What I built

AI triage that answers only from approved replies and a curated knowledge base. Sensitive cases always go to a person. It automates triage, not judgment.

```mermaid
flowchart TD
    T[New or open ticket in Zendesk] --> G1{Protected case?<br/>refund, billing dispute,<br/>unrecognised charge,<br/>very frustrated customer,<br/>lifetime membership}
    G1 -- yes --> H[Held for the support lead]
    G1 -- no --> AI[One AI classification pass]
    AI --> C{Choice}
    C -- approved reply --> R[Fill one of the<br/>human-approved templates]
    C -- knowledge-base answer --> K[Deterministic check<br/>before it can send]
    C -- unsure / duplicate --> H
    K -- fails --> H
    K -- passes --> S[Send]
    R --> S
    S --> L[Close only on a real<br/>customer signal]
    S --> REP[Run report and run history]
    REP --> D[Review dashboard:<br/>needs attention first]
    D --> Q[Weekly quality review<br/>+ AI second-opinion audit<br/>of solved tickets]
```

## Design choices

- **Constrained AI.** The model may only pick from a fixed set of human-approved replies (18 templates) or answer from the knowledge base. It never writes free text to a customer without a deterministic check.
- **Safety gates in code, not in the prompt.** Refunds, disputes and other protected cases are caught by rules before the AI sees them.
- **Dry run first.** Every run can be done as a dry run. One dry run over 332 tickets found 22 real duplicates, and all were correctly held for review.
- **Everything is checkable.** A report for every run, a run history, a review dashboard, a weekly quality review and an AI audit that re-reads solved tickets. Every bug found became a regression test.
- **Security.** Keys in a separate auto-locking keychain, dedicated expiring keys, a monthly API spend limit, Zendesk rate limiting, certificate verification on every API call.
- **Cost.** About 1 cent of AI cost per ticket.

## Results

From 1 September to 22 October 2026, live runs only, from the system's own run log:

| | September | October (to 22nd) | Total |
|---|---|---|---|
| New tickets handled | 972 | 660 | **1,632** |
| Answered in full | 395 (41%) | 162 (25%) | **557 (34%)** |
| Immediate first reply, then a person | 367 | 297 | **664 (41%)** |
| Sent straight to a person (money, privacy, unclear) | 30 | 43 | **73 (4%)** |
| Junk, duplicates and business mail filtered out | 180 | 158 | **338** |
| Follow-ups sent | 27 | 158 | **185** |
| Closed once the customer confirmed | 87 | 155 | **242** |

- September includes clearing the backlog: the first live run over the whole queue handled 337 tickets with zero errors.
- No errors found in weekly quality audits. Nobody was removed from a role.

## Incident review

After a customer incident, I led a review of the full ticket history (1,995 tickets) for refund confirmations that had never been verified. The findings became permanent safety checks in the system.

## Code

A standalone version in Python, with tests, that follows this design and reproduces the results above: [code/triage](../code/triage/).

## Stack

Zendesk API · Claude API · SQLite (run history) · Notion (weekly review) · Claude Code

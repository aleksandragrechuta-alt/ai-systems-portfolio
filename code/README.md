# CX automation in code: reaching out, and answering

Customer experience has two sides: **reaching out** to customers first, and **answering** them when they write. I have built and run automation for both, with the same principles: rules first, AI only where judgment is needed, a person in control of anything sensitive, and every decision logged and reviewed.

| | Answering: [`support/`](support/) | Reaching out: [`outreach/`](outreach/) |
|---|---|---|
| **What it does** | Reads every incoming support ticket and decides: answer it in full, send an immediate first reply and pass it to a person, pass it straight to a person, or filter it out | Researches stores, drafts a personal email for each, sends it only after approval and in the recipient's morning, follows up, and reads the replies |
| **Where the AI decides** | What the customer is asking, choosing only from approved replies and a curated knowledge base | The draft of each email, checked against writing rules before a person sees it |
| **Where a person decides** | Refunds, billing disputes, privacy, very frustrated customers, anything unclear | Every send: nothing goes out until a person approves it |
| **Safety in code** | Protected cases caught before the AI; fixed checks on every answer; failure means a person | Verified addresses only; never the same company twice; daily limits; bounces and automatic replies recognised |
| **How it is reviewed** | Run history and a performance review: outcomes, attention list, knowledge gaps, quality audit sample | Log of every action, run report, review app |
| **Live results** | 1,632 tickets from 1 Sep to 22 Oct 2026, 75% answered or given a first reply at once, no errors in weekly audits | Live since September 2026, used by me and our sales representative |
| **Code here** | A standalone version written for this portfolio, following the live design and reproducing the live numbers. The live code is private because it holds client data. | Copied from the live pipeline |

The two systems run for two different businesses and are not connected to each other. Together they show the full loop a CX automation needs: start the conversation well, answer well, hand over to a person at the right moment, and learn from every run. Connecting them, so a customer's outreach history and support history live in one record, would be the natural next step.

All of it was built with AI coding assistants (Claude Code): I define the problem, the rules and the safety limits, review the results against real data, and run the systems.

Both folders run in Python 3.10 or newer, with no extra packages:

```bash
cd code/support && python3 -m unittest && python3 demo.py
cd ../outreach && python3 -m unittest
```

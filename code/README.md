# Code

Two systems, shown in code. Both run in Python with no extra packages, and both have tests.

| Folder | What it is | Where it comes from |
|---|---|---|
| [`triage/`](triage/) | AI-assisted support triage: filtering, safety rules, the helpdesk API connection, run history and the performance review, reproducing the live system's real results (1,632 tickets, 75% answered or given a first reply at once) | A standalone version written for this portfolio, following the design of the live system. The live code is private because it holds client data. |
| [`outreach/`](outreach/) | The send rules of the B2B outreach pipeline: approval, writing rules, verified addresses, no double contact, the recipient's morning, daily limits, bounces and automatic replies | Copied from the live pipeline. |

All of it was built with AI coding assistants (Claude Code): I define the problem, the rules and the safety limits, review the results against real data, and run the systems.

```bash
cd code/triage && python3 -m unittest && python3 demo.py
cd ../outreach && python3 -m unittest
```

# B2B outreach pipeline (Mur Mur Objects)

**Context:** my own lighting brand, [murmurobjects.com](https://murmurobjects.com). **Status:** live; the current version (v6) runs since September 2026. It replaced an earlier Google Apps Script version.

## The problem

Wholesale growth depends on writing to many independent shops, following up and answering replies quickly. It is work for two people: me and our sales representative. It needs to sound personal and on-brand, and nothing should go out by mistake.

## What I built

A Python pipeline that runs every hour on GitHub Actions and works from a Google Sheet (one tab per sender, plus press and influencers).

```mermaid
flowchart TD
    N[New prospect row in the sheet] --> DUP{Duplicate?}
    DUP -- yes --> X[Skipped]
    DUP -- no --> RES[AI research of the store]
    RES --> DR[AI-drafted personal email<br/>in the brand voice]
    DR --> BW{Banned-words check}
    BW -- fails --> DR
    BW -- passes --> AP{Row set to APPROVED<br/>by a person?}
    AP -- not yet --> W[Waits]
    AP -- yes --> TIME{Recipient's local morning<br/>and under the daily<br/>mailbox limit?}
    TIME -- no --> W
    TIME -- yes --> SEND[Send]
    SEND --> FU[Follow-up after 7 days]
    SEND --> IN[Inbox check]
    IN --> B[Bounce or auto-reply detected]
    IN --> OPT[Opt-out: set to Do Not Contact]
    IN --> REPLY[Real reply: AI scores it and<br/>drafts an answer in the contact's language]
    REPLY --> AP2{Approved?}
    AP2 -- yes --> SEND2[Answer sent]
```

## Design choices

- **Nothing reaches a real contact without approval.** First emails and reply answers both wait for a person.
- **Sends like a person would.** Only in the recipient's local morning, and within a daily limit per mailbox.
- **Brand voice is enforced.** Drafts are checked against a banned-words list before they can be approved.
- **Inbox hygiene is automatic.** Bounces, auto-replies and opt-outs are handled without manual work.

## Code

The send rules, copied from the live pipeline, with tests: [code/outreach](../code/outreach/).

## Stack

Python · Claude API · Google Sheets API · Gmail · GitHub Actions · Claude Code
